# 获取最新代码

```bash
git fetch origin
```

- **作用**：从远程仓库获取最新的分支、提交和标签信息，更新本地的 `origin/*` 远程跟踪分支，但不会修改当前工作区或本地分支。
- **`fetch`**：下载远程仓库的最新 Git 对象和引用。
- **`origin`**：远程仓库名称，通常指向项目的主 GitHub 仓库。

```bash
git switch main
```

- **作用**：将当前本地分支切换到 `main`，后续更新、备份和合并操作都以 `main` 为基础执行。
- **`switch`**：切换分支的 Git 子命令。
- **`main`**：要切换到的本地生产分支。

```bash
git pull --ff-only origin main
```

- **作用**：从远程 `origin` 拉取最新的 `main`，并仅允许使用 fast-forward（快进）方式更新当前本地 `main`。
- **`pull`**：先获取远程更新，再将指定远程分支整合到当前本地分支。
- **`--ff-only`**：只允许快进更新。如果本地 `main` 与远程 `main` 已分叉，命令会拒绝合并，避免意外生成合并提交。
- **`origin`**：要拉取的远程仓库。
- **`main`**：要拉取的远程分支。

# 创建并推送备份分支

```bash
backup_branch="backup/main-$(date +%Y%m%d-%H%M%S)"
```

- **作用**：生成带当前日期和时间的唯一备份分支名，并保存到 Shell 变量 `backup_branch`。例如：`backup/main-20260923-103015`。
- **`backup_branch=...`**：定义 Shell 变量；这不是 Git 命令。
- **`$(...)`**：Shell 命令替换，执行括号中的命令，并将输出放入变量值。
- **`date +%Y%m%d-%H%M%S`**：按“年4位 + 月2位 + 日2位-时2位 + 分2位 + 秒2位”格式生成时间戳。

```bash
git branch "$backup_branch"
```

- **作用**：以当前 `main` 的 HEAD 提交为起点创建本地备份分支，但不切换到该备份分支。
- **`branch`**：创建、查看或管理分支的 Git 子命令。这里由于提供了新分支名，因此执行创建操作。
- **`"$backup_branch"`**：展开为上一步生成的备份分支名。双引号可防止 Shell 对变量内容进行不必要的分词或通配符展开。

```bash
git push origin "$backup_branch"
```

- **作用**：将新建的本地备份分支推送到远程仓库，使合并前的 `main` 状态在远程也有可恢复的引用。
- **`push`**：将本地提交和分支引用上传到远程仓库。
- **`origin`**：接收备份分支的远程仓库。
- **`"$backup_branch"`**：要推送的本地分支名。在远程未指定其他名称时，会创建同名远程分支。

# 合并 testing，保留独立合并提交，方便回滚

```bash
git merge --no-ff origin/testing -m "Release testing to main"
```

- **作用**：将已获取到本地的远程跟踪分支 `origin/testing` 合并到当前 `main`，并强制生成一个独立的合并提交。
- **`merge`**：将指定分支的历史整合到当前分支。
- **`--no-ff`**：即使当前分支可以直接快进，也要创建合并提交。这样可明确记录每次发布的边界，也便于将整次发布作为一个单元进行回滚。
- **`origin/testing`**：上一步 `git fetch origin` 更新的远程 `testing` 跟踪分支。
- **`-m "Release testing to main"`**：直接指定合并提交的 commit message，避免 Git 打开交互式编辑器。

# 合并成功后推送

```bash
git push origin main
```

- **作用**：将包含新合并提交的本地 `main` 推送到远程 `origin/main`，完成生产分支发布。
- **`push`**：将本地提交和分支引用上传到远程仓库。
- **`origin`**：目标远程仓库。
- **`main`**：要推送的本地分支。默认情况下它会更新同名的远程 `main` 分支。

# 回滚已发布的 testing 合并

如果合并到 `main` 并推送后发现问题，推荐通过 `git revert` 生成新的回滚提交。这种方式保留完整历史，不会改写共享 `main` 的提交记录。

## 1. 同步最新 main

```bash
git fetch origin
git switch main
git pull --ff-only origin main
```

- **作用**：获取远程最新状态，切换到本地 `main`，并将它快进到最新的 `origin/main`。
- **`git fetch origin`**：更新 `origin/*` 远程跟踪分支，不修改当前工作区。
- **`git switch main`**：切换到本地 `main` 分支。
- **`git pull --ff-only origin main`**：只允许以快进方式用 `origin/main` 更新本地 `main`；如果两者已分叉则拒绝执行。

## 2. 查找要回滚的发布合并提交

```bash
git log --merges --oneline origin/main
```

- **作用**：查看 `origin/main` 上的合并提交，找到 commit message 为 `Release testing to main` 的目标发布提交，并记录它的 commit SHA。
- **`log`**：查看提交历史。
- **`--merges`**：只显示合并提交。
- **`--oneline`**：每个提交仅显示一行，包含缩写 SHA 和 commit message。
- **`origin/main`**：要查看的远程 `main` 跟踪分支。

将找到的 SHA 保存到 Shell 变量：

```bash
merge_commit="<merge_commit_sha>"
```

- **作用**：将要回滚的合并提交 SHA 保存到 `merge_commit` 变量。
- **`<merge_commit_sha>`**：需要替换为上一步查到的真实 SHA，例如 `abc1234`。
- 这是 Shell 变量赋值，不是 Git 命令。

## 3. 生成回滚提交

```bash
git revert -m 1 "$merge_commit"
```

- **作用**：生成一个新提交，撤销指定合并提交带入 `main` 的变更，但不删除原合并提交。
- **`revert`**：创建一个反向提交，用于安全撤销已共享的提交。
- **`-m 1`**：指定合并提交的第 1 个父提交为 mainline（主线）。在本流程中，第 1 个父提交是合并前的 `main`，因此 Git 会撤销由 `testing` 带入的变更。
- **`"$merge_commit"`**：展开为要回滚的合并提交 SHA。

Git 通常会打开编辑器显示默认回滚信息；保存并退出编辑器后即会创建回滚提交。

## 4. 如果回滚时出现冲突

先查看冲突文件：

```bash
git status
```

- **作用**：显示当前 revert 进度、冲突文件和可执行的后续操作。
- **`status`**：查看工作区、暂存区和当前 Git 操作状态。

手动修复冲突后，将已解决的文件加入暂存区：

```bash
git add <resolved_file>
```

- **作用**：标记指定文件的冲突已解决。
- **`add`**：将文件当前内容加入暂存区。
- **`<resolved_file>`**：需替换为已手动修复的实际文件路径。

所有冲突都解决后继续回滚：

```bash
git revert --continue
```

- **作用**：在冲突文件已解决并暂存后，继续执行之前暂停的 revert，并创建回滚提交。
- **`--continue`**：继续当前因冲突而暂停的 revert 操作。

如果不想继续本次回滚，可以取消：

```bash
git revert --abort
```

- **作用**：取消当前尚未完成的 revert，将工作区和分支恢复到开始 revert 之前的状态。
- **`--abort`**：终止当前 revert 过程。

> `git revert --continue` 和 `git revert --abort` 二选一：解决冲突后继续，或取消整个回滚操作。

## 5. 检查并推送回滚提交

```bash
git show --stat --oneline HEAD
```

- **作用**：在推送前检查最新回滚提交的说明和文件变更统计。
- **`show`**：显示指定 Git 对象，这里是最新提交。
- **`--stat`**：显示变更文件、行数和增删统计。
- **`--oneline`**：使提交标题以紧凑的单行形式显示。
- **`HEAD`**：当前分支最新的提交，此时应为新创建的回滚提交。

```bash
git push origin main
```

- **作用**：将回滚提交推送到 `origin/main`，使远程生产分支恢复到撤销该次发布变更后的状态。
- **`push`**：将本地提交和分支引用上传到远程仓库。
- **`origin`**：目标远程仓库。
- **`main`**：要推送的本地生产分支。

> 不要对共享的 `main` 使用 force-push 或通过改写历史的方式回滚。使用 revert 提交能保留完整、可审计的发布和回滚记录。
