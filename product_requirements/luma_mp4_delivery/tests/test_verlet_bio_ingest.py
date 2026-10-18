"""The verlet Biology Lab ingest: bucket discovery and the calibration sidecar.

Driven by a fake S3 client, so the bucket shape these tests pin is asserted
rather than fetched -- and so a change to the supplier's layout fails here
rather than in a job at 3am.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tests"),
           os.path.join(_ROOT, "workers", "verlet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from pg_test_util import temp_db_url  # noqa: E402
from staging import Config, FileKind, StagingStore  # noqa: E402

import bio_ingest  # noqa: E402  (workers/verlet/)

PFX = "verlet-bio-mcap-unreviewed"


def _episode(folder: str, ep: str, *, sizes=(10, 20, 30, 40)):
    """The four keys of one episode, in the supplier's nested layout."""
    base = f"{folder}/{ep}"
    return {
        f"{PFX}/{base}.mcap": sizes[0],
        f"{PFX}/{base}/cam_high.mp4": sizes[1],
        f"{PFX}/{base}/cam_left.mp4": sizes[2],
        f"{PFX}/{base}/cam_right.mp4": sizes[3],
    }


def _manifest(folder: str, ep: str, *, status="completed", excluded=False,
              audit_clean=True, drop=()):
    base = f"{folder}/{ep}"
    arts = [f"{base}.mcap", f"{base}/cam_high.mp4",
            f"{base}/cam_left.mp4", f"{base}/cam_right.mp4"]
    arts = [a for a in arts if not any(d in a for d in drop)]
    return {"payload_prefix": base, "status": status, "excluded": excluded,
            "audit_clean": audit_clean, "episode_id": f"id-{ep}",
            "artifacts": [{"path": p, "size_bytes": 1} for p in arts]}


class FakeS3:
    """Just the three calls :mod:`bio_ingest` makes."""

    def __init__(self, objects: dict, docs: dict):
        self.objects = dict(objects)
        self.docs = dict(docs)
        for key in docs:
            self.objects.setdefault(key, 1)

    def get_paginator(self, _name):
        outer = self

        class _P:
            def paginate(self, Bucket=None, Prefix="", **_kw):  # noqa: N803
                yield {"Contents": [{"Key": k, "Size": v}
                                    for k, v in sorted(outer.objects.items())
                                    if k.startswith(Prefix)]}
        return _P()

    def get_object(self, Bucket=None, Key=None):  # noqa: N803
        if Key not in self.docs:
            raise KeyError(Key)
        return {"Body": io.BytesIO(json.dumps(self.docs[Key]).encode())}


def _bucket(entries):
    """``entries`` = list of (folder, ep, manifest-kwargs)."""
    objs, docs = {}, {}
    for folder, ep, kw in entries:
        objs.update(_episode(folder, ep))
        docs[f"{PFX}/_status/{ep}.json"] = _manifest(folder, ep, **kw)
    return objs, docs


def test_discovery_reads_the_manifest_not_the_key_shape():
    """The episode dir is repeated and the mcap sits a level up.

    ``<payload_prefix>/<episode_dir>/cam_high.mp4`` but
    ``<payload_prefix>.mcap`` -- so a discovery that parsed key segments would
    file the mcap under a folder of its own.  The manifest names every key.
    """
    objs, docs = _bucket([("bio_new_1", "bio_new_1_aa_ep0", {})])
    eps, excluded, incomplete = bio_ingest.discover(FakeS3(objs, docs),
                                                    prefixes=[PFX])
    assert len(eps) == 1, (eps, incomplete)
    ep = eps[0]
    assert ep.episode_dir == "bio_new_1_aa_ep0"
    assert ep.mcap[0].endswith("bio_new_1_aa_ep0.mcap")
    assert [os.path.basename(k) for k, _ in ep.videos] == list(bio_ingest.RGB_VIDEOS)
    assert not excluded and not incomplete
    print("bio: discovery follows the manifest, not the key shape OK")


def test_incomplete_and_excluded_episodes_are_separated():
    """'Not ready yet' is skipped silently; 'the supplier said no' is reported."""
    objs, docs = _bucket([
        ("f1", "ok_ep0", {}),
        ("f2", "pending_ep0", {"status": "uploading"}),
        ("f3", "dropped_ep0", {"excluded": True}),
        ("f4", "dirty_ep0", {"audit_clean": False}),
    ])
    # An episode whose manifest lists media that has not landed.
    objs.update(_episode("f5", "half_ep0"))
    docs[f"{PFX}/_status/half_ep0.json"] = _manifest("f5", "half_ep0")
    del objs[f"{PFX}/f5/half_ep0/cam_left.mp4"]

    eps, excluded, incomplete = bio_ingest.discover(FakeS3(objs, docs),
                                                    prefixes=[PFX])
    assert [e.episode_dir for e in eps] == ["ok_ep0"], eps
    assert len(excluded) == 3, excluded          # uploading + excluded + dirty
    assert any("not all landed" in i for i in incomplete), incomplete
    print("bio: incomplete and excluded episodes are separated OK")


def test_the_prefix_sidecar_is_not_mistaken_for_media():
    """``dataset_info.json`` is calibration, not an episode.

    Counted as media it becomes a phantom episode whose manifest never arrives,
    reported on every single run.
    """
    objs, docs = _bucket([("f1", "ok_ep0", {})])
    objs[f"{PFX}/{bio_ingest.DATASET_INFO}"] = 4096
    _eps, _ex, incomplete = bio_ingest.discover(FakeS3(objs, docs), prefixes=[PFX])
    assert not any(bio_ingest.DATASET_INFO in i for i in incomplete), incomplete
    print("bio: the prefix sidecar is not mistaken for media OK")


def test_calibration_is_keyed_on_prefix_and_directory():
    """One directory exists under *both* prefixes with different limits.

    Keyed on the directory alone, the lookup silently resolves to whichever
    prefix was read last -- staging 30908 would have carried the wrong arm
    calibration.
    """
    shared = "bio_new_1342_dd_ep0"
    docs = {}
    for prefix, closed in (("verlet-bio-mcap", 6.30),
                           ("verlet-bio-mcap-unreviewed", 6.35)):
        docs[f"{prefix}/{bio_ingest.DATASET_INFO}"] = {
            "schema_version": 1, "dataset": {"robot_type": "i2rt_yam_bimanual"},
            "gripper_calibration": {"units": "motor_radians", "episodes": {
                f"bio_new_1342/{shared}": {
                    "episode_id": f"eid-{prefix}",
                    "gripper_limits": {"left": {"closed_rad": closed, "open_rad": 1.0},
                                       "right": {"closed_rad": closed, "open_rad": 1.0}},
                    "source": {"left": "measured", "right": "measured"}}}}}
    cal = bio_ingest.load_calibration(FakeS3({}, docs))
    assert set(cal) == {("verlet-bio-mcap", shared),
                        ("verlet-bio-mcap-unreviewed", shared)}, sorted(cal)

    # ...and an idempotency key says which one an episode belongs to.
    assert bio_ingest.bucket_prefix_of("verlet-bio-unrev-" + shared) == \
        ("verlet-bio-mcap-unreviewed", shared)
    assert bio_ingest.bucket_prefix_of("verlet-bio-mcap-" + shared) == \
        ("verlet-bio-mcap", shared)
    assert bio_ingest.bucket_prefix_of("something-else") is None
    print("bio: calibration is keyed on (prefix, directory) OK")


def _entry(closed=6.3, open_=1.0, robot="i2rt_yam_bimanual"):
    doc = {"schema_version": 1, "generated_at": "2026-09-03T00:00:00+00:00",
           "dataset": {"robot_type": robot} if robot else {}}
    header = {"units": "motor_radians", "convention": "angle = ..."}
    entry = {"episode_id": "eid",
             "gripper_limits": {"left": {"closed_rad": closed, "open_rad": open_},
                                "right": {"closed_rad": closed, "open_rad": open_}},
             "source": {"left": "measured", "right": "measured"}}
    return ("verlet-bio-mcap", "k", doc, header, entry)


def test_a_sidecar_that_cannot_be_trusted_is_refused():
    """A degenerate span divides by ~zero in the delivery; it must not ship."""
    good = bio_ingest.sidecar_for(1, "ep", *_entry())
    assert bio_ingest.sidecar_problems(good) == []
    assert good["gripper_calibration"]["arms"]["left"]["leader_topic"] == \
        "/robot/arm_left_leader/joint_states"

    degenerate = bio_ingest.sidecar_for(1, "ep", *_entry(closed=4.2, open_=4.2))
    assert any("degenerate" in p for p in bio_ingest.sidecar_problems(degenerate))

    no_robot = bio_ingest.sidecar_for(1, "ep", *_entry(robot=""))
    assert any("robot_type" in p for p in bio_ingest.sidecar_problems(no_robot))
    print("bio: an untrustworthy sidecar is refused OK")


def test_the_sidecar_is_registered_as_metadata_not_raw():
    """RAW is reclaimable, and this is a delivery *precondition*.

    Filed under ``raw`` it would be deleted by an ordinary reclamation and the
    episode would quietly stop being deliverable.
    """
    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                   supplier="verlet", task_name="Biology Lab",
                                   length_seconds=1.0, episode_format="mp4")
        sidecar = bio_ingest.sidecar_for(sid, "ep", *_entry())
        path, action = bio_ingest.write_sidecar(store, sid, sidecar)
        assert action == "registered"
        row = store.db.query_one(
            "SELECT kind, original_name FROM files WHERE staging_id = ? "
            "AND original_name = ?", (sid, bio_ingest.SIDECAR_BASENAME))
        assert row["kind"] == FileKind.METADATA.value, dict(row)
        assert json.load(open(path))["staging_id"] == sid

        # Writing again refreshes in place rather than registering a duplicate.
        _p2, action2 = bio_ingest.write_sidecar(store, sid, sidecar)
        assert action2 == "refreshed"
        n = store.db.query_one(
            "SELECT COUNT(*) AS n FROM files WHERE staging_id = ? "
            "AND original_name = ?", (sid, bio_ingest.SIDECAR_BASENAME))["n"]
        assert int(n) == 1, n
        store.close()
    print("bio: the sidecar is registered as metadata and refreshes OK")


def test_missing_credentials_fail_before_anything_is_listed():
    """A job that cannot reach the bucket should say so in its first line."""
    saved = {k: os.environ.pop(k, None)
             for k in ("R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY")}
    try:
        with pytest.raises(bio_ingest.CredentialsMissing) as exc:
            bio_ingest.client()
        assert "R2_ENDPOINT" in str(exc.value)
        assert "actuate-webui.env" in str(exc.value)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    print("bio: missing credentials fail early and say where to put them OK")


def test_a_promoted_re_export_is_not_ingested_twice():
    """The two prefixes are a pipeline, not a partition.

    The supplier promotes a reviewed episode by **re-exporting** it into
    ``verlet-bio-mcap`` -- same recording, different bytes.  Treated as a
    partition, that reviewed copy looks like an episode we have never seen, and
    ingesting it duplicates a recording we already hold.  It happened at scale:
    810 of 1,095 "new" episodes on 2026-09-05.
    """
    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))

        def episode(key):
            return store.create_episode(
                robot_type="yam", uploader_identity="verlet", supplier="verlet",
                task_name="Biology Lab", length_seconds=1.0,
                episode_format="mp4", idempotency_key=key)

        held = "bio_new_1_aa_ep0"
        episode(bio_ingest.PREFIXES["verlet-bio-mcap-unreviewed"] + held)

        class _Ep:
            def __init__(self, prefix, ep):
                self.prefix, self.episode_dir = prefix, ep

            @property
            def idempotency_key(self):
                return bio_ingest.PREFIXES[self.prefix] + self.episode_dir

        promoted_copy = _Ep("verlet-bio-mcap", held)          # same recording
        genuinely_new = _Ep("verlet-bio-mcap", "bio_new_2_bb_ep0")
        same_key_again = _Ep("verlet-bio-mcap-unreviewed", held)

        todo, promoted = bio_ingest.pending(
            store, [promoted_copy, genuinely_new, same_key_again])
        assert [e.episode_dir for e in todo] == ["bio_new_2_bb_ep0"], todo
        assert [e.episode_dir for e in promoted] == [held], promoted
        # ...and the promoted copy is *reported*, not silently dropped: a run
        # that skipped 810 episodes without saying so reads like a broken one.
        assert len(promoted) == 1
        store.close()
    print("bio: a promoted re-export is not ingested twice OK")


def _mcap(path, record=None):
    """A minimal MCAP, optionally carrying a ``gripper_limits`` record."""
    from mcap.writer import Writer

    with open(path, "wb") as fh:
        w = Writer(fh)
        w.start()
        if record is not None:
            w.add_metadata(bio_ingest.MCAP_CALIBRATION_RECORD,
                           {k: str(v) for k, v in record.items()})
        w.finish()


def _record(lc=6.3, lo=1.0, rc=5.3, ro=-0.01):
    return {"left_closed_rad": lc, "left_open_rad": lo,
            "right_closed_rad": rc, "right_open_rad": ro,
            "units": "motor_radians", "convention": "angle = ...",
            "left_source": "measured", "right_source": "measured"}


def _episode_with_mcap(store, tmp, ep_dir, record):
    sid = store.create_episode(
        robot_type="yam", uploader_identity="verlet", supplier="verlet",
        task_name="Biology Lab", length_seconds=1.0, episode_format="mp4",
        idempotency_key=bio_ingest.PREFIXES["verlet-bio-mcap"] + ep_dir)
    p = os.path.join(tmp, f"{ep_dir}.mcap")
    _mcap(p, record)
    store.add_files(sid, [p], FileKind.RAW)
    return sid


def test_calibration_comes_from_our_own_mcap():
    """Read from the ``gripper_limits`` record of the MCAP we hold.

    Not the bucket's copy: a re-export can move the gripper's raw zero point.
    Staging 32588's bucket copy reads left (0.046, -5.276) while ours reads
    (6.327, 0.982) -- each right for its own bytes.
    """
    ep = "bio_new_1_aa11bb22-9372ecc6_ep000005"
    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        sid = _episode_with_mcap(store, tmp, ep, _record())
        rig = {"rig_id": "teleop_station_rw-08", "urdf": "teleop_station_rw-08.urdf"}
        sidecar, action = bio_ingest.resolve_sidecar(
            store, sid, robots={"9372ecc6": rig}, episode_id="eid-1")
        assert action == "write", action
        arms = sidecar["gripper_calibration"]["arms"]
        assert (arms["left"]["closed_rad"], arms["left"]["open_rad"]) == (6.3, 1.0)
        assert (arms["right"]["closed_rad"], arms["right"]["open_rad"]) == (5.3, -0.01)
        assert sidecar["robot"]["rig_id"] == "teleop_station_rw-08"
        assert sidecar["supplier_episode_id"] == "eid-1"
        assert sidecar["provenance"]["source"] == "mcap_metadata"
        bio_ingest.write_sidecar(store, sid, sidecar)

        # Agreeing with what is on file, it is left alone -- provenance included.
        again, action2 = bio_ingest.resolve_sidecar(store, sid)
        assert (again, action2) == (None, "unchanged"), action2
        store.close()
    print("bio: calibration comes from our own MCAP OK")


def test_an_export_without_the_record_keeps_its_sidecar():
    """Pre-2026-09-03 exports carry no record, but their sidecar is still right.

    It was built from the ``dataset_info.json`` that described exactly those
    bytes.  With neither a record nor a sidecar the episode is held back.
    """
    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        kept = _episode_with_mcap(store, tmp, "bio_new_2_cc-7b8c7b1d_ep000000", None)
        bio_ingest.write_sidecar(store, kept,
                                 bio_ingest.sidecar_for(kept, "ep", *_entry()))
        assert bio_ingest.resolve_sidecar(store, kept) == (None, "kept")

        bare = _episode_with_mcap(store, tmp, "bio_new_3_dd-7b8c7b1d_ep000000", None)
        with pytest.raises(RuntimeError, match="no sidecar on file"):
            bio_ingest.resolve_sidecar(store, bare)
        store.close()
    print("bio: a record-less export keeps its sidecar; neither -> held back OK")


def test_a_sidecar_that_disagrees_with_its_mcap_is_rewritten():
    """The MCAP we deliver is the authority; a stale sidecar is replaced."""
    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        sid = _episode_with_mcap(store, tmp, "bio_new_4_ee-579c7b70_ep000001",
                                 _record(lc=0.046, lo=-5.276))
        bio_ingest.write_sidecar(store, sid,
                                 bio_ingest.sidecar_for(sid, "ep", *_entry()))
        sidecar, action = bio_ingest.resolve_sidecar(store, sid)
        assert action == "write"
        assert sidecar["gripper_calibration"]["arms"]["left"]["open_rad"] == -5.276
        store.close()
    print("bio: a sidecar that disagrees with its MCAP is rewritten OK")


def test_the_robots_tree_is_not_mistaken_for_episodes():
    """URDFs and meshes per rig, not media waiting for a manifest."""
    objs, docs = _bucket([("f1", "ok_ep0", {})])
    objs[f"{PFX}/robots/index.json"] = 1023
    objs[f"{PFX}/robots/teleop_station_rw-05.urdf"] = 63642
    objs[f"{PFX}/robots/meshes/d405.stl"] = 530484
    eps, _ex, incomplete = bio_ingest.discover(FakeS3(objs, docs), prefixes=[PFX])
    assert len(eps) == 1
    assert not any("robots" in i for i in incomplete), incomplete
    print("bio: the robots tree is not mistaken for episodes OK")


def test_the_station_is_read_off_the_episode_directory():
    assert bio_ingest.station_of("bio_new_1115_2eef9edf-9372ecc6_ep000005") == "9372ecc6"
    assert bio_ingest.station_of(
        "bio_new_1497_organizing_tubes_of_different_specifications_in_"
        "bdc4b803-9372ecc6_ep000016") == "9372ecc6"
    assert bio_ingest.station_of("not_an_episode") is None
    print("bio: the station is read off the episode directory OK")


def test_the_job_checks_calibration_and_writes_no_sidecar():
    """The job's per-episode step is a check through the delivery's own loader.

    The delivery reads the ``gripper_limits`` record straight from the MCAP, so
    an episode carrying one needs nothing written.  A record-less export still
    passes on its legacy sidecar; one with neither fails the episode, so it
    shows in the run instead of silently never becoming a Luma candidate.
    """
    from webui2.jobs import kinds

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        good = _episode_with_mcap(store, tmp, "bio_new_5_ff-9372ecc6_ep000001",
                                  _record())
        assert kinds._verlet_bio_one(store, good, {}, print) == {
            "staging_id": good, "calibrated": True}
        assert bio_ingest.sidecar_row(store, good) is None, "wrote a sidecar"

        legacy = _episode_with_mcap(store, tmp, "bio_new_6_gg-7b8c7b1d_ep000000",
                                    None)
        bio_ingest.write_sidecar(store, legacy,
                                 bio_ingest.sidecar_for(legacy, "ep", *_entry()))
        assert kinds._verlet_bio_one(store, legacy, {}, print)["calibrated"]

        bare = _episode_with_mcap(store, tmp, "bio_new_7_hh-7b8c7b1d_ep000000",
                                  None)
        with pytest.raises(RuntimeError, match="no usable gripper calibration"):
            kinds._verlet_bio_one(store, bare, {}, print)
        store.close()
    print("bio: the job checks calibration and writes no sidecar OK")


def test_the_fetch_loop_stops_on_cancel_and_before_the_disk_floor(monkeypatch):
    """The fetch honours a cancel and the free-space floor between episodes.

    Both runner checks sit in the calibration pass, after the whole fetch.  On
    2026-09-14 a cancelled run kept fetching for 93 minutes and its last 914
    episodes failed ENOSPC; a nightly run has nobody watching it.
    """
    from staging import diskspace
    from webui2.jobs import kinds

    gib = 1024 ** 3

    class _Ep:
        def __init__(self, n):
            self.episode_dir = f"bio_new_{n}_aa-9372ecc6_ep{n:06d}"
            self.total_bytes = 5 * gib
            self.episode_id = f"e{n}"

    eps = [_Ep(n) for n in range(4)]
    fetched: list = []
    free = {"bytes": 10 ** 15}
    monkeypatch.setattr(bio_ingest, "client", lambda: object())
    monkeypatch.setattr(bio_ingest, "discover",
                        lambda s3, log=None: (list(eps), [], []))
    monkeypatch.setattr(bio_ingest, "pending",
                        lambda store, episodes: (list(episodes), []))
    monkeypatch.setattr(bio_ingest, "ingest_one",
                        lambda s3, ep, **kw: fetched.append(ep) or len(fetched))
    monkeypatch.setattr(diskspace, "free_bytes_for_path",
                        lambda path: free["bytes"])

    with tempfile.TemporaryDirectory() as tmp:
        class _Store:
            def active_data_root(self):
                return tmp

        params = {"upload_id": 999, "server": "http://unused"}

        # Room for everything: all four are fetched.
        out = kinds._verlet_bio_prepare(_Store(), dict(params), print)
        assert out["ingested"] == 4 and len(fetched) == 4

        # A cancel lands after the second fetch.
        fetched.clear()
        cancel = dict(params, _cancel=lambda: len(fetched) >= 2)
        assert kinds._verlet_bio_prepare(_Store(), cancel, print)["ingested"] == 2

        # One byte short of the floor plus twice an episode: nothing is fetched.
        fetched.clear()
        free["bytes"] = diskspace.MIN_FREE_BYTES + 2 * 5 * gib - 1
        assert kinds._verlet_bio_prepare(_Store(), dict(params), print)["ingested"] == 0
        assert not fetched
    print("bio: the fetch loop stops on cancel and before the disk floor OK")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
