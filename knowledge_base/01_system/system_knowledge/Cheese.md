# Fresh Cheese — Prompt 使用指南

> 内部资料 · Fresh Cheese WebUI 与 Claude Code 查询说明

## 访问地址

- WebUI：[http://fresh-cheese.com/](http://fresh-cheese.com/)
- 密码：`oliverisamanworm`

## 使用说明

使用自然语言提问即可。Claude 会通过 `psql` 直接查询生产数据库，并读取 `AGENTS.md`（其中记录了系统的工作规则）。因此，它计算工时的方式与 Customers 页签一致，同时还能按任意维度拆分结果。它也可以打开原始 MCAP 和视频，而 UI 无法完成这些工作。

进入节点后，建议使用 `/resume` 恢复旧会话。否则，请在第一条 Prompt 中写明：

> We are on webui v2 and database v2.

旧代码库和旧数据库尚未删除；如果不说明，Claude 有时会选错数据库。

## Prompt 示例

### 上传完整性排查 （ by Wanxin)

> We are on webui v2 and database v2. VLA Foundry is reporting: "the upload from yun team #441 seems not fully uploaded to our VLA system. It has 177 episodes in total, but in our VLA, it seems upload broken once and still not fully uploaded. currently only 10+26 episodes in our raw buckets."

### 交付和工时统计

> How many hours of Block manipulation and Biology Lab were delivered to Luma and not marked as FAIL?  
> 有多少小时的 Block manipulation 和 Biology Lab 已交付给 Luma，并且没有被标记为 FAIL？

> What are the total hours from yun for the Block manipulation task? Break down total hours, delivered hours to Luma, accepted hours, and undelivered.  
> yun 的 Block manipulation Task 总共有多少小时？请拆分为总工时、已交付给 Luma 的工时、已接受工时和未交付工时。

### 列表和电子表格

> Can you pull a CSV of all the uploaded episode_id, original mcap filename, and lengths for yun Block manipulation tasks?  
> 请导出 yun 的 Block manipulation Task 中所有已上传 Episode 的 `episode_id`、原始 MCAP 文件名和时长 CSV。

**必须说明文件保存位置**，例如：“put it in `user_files/`”。否则文件会落在之后可能被清理的临时目录中。

### 缺失或标签错误的 Episode

> Help us chase down the mislabelled episodes in episodes.jpg — their labels don't match anything in the task_id column of tasks.xlsx.  
> 帮助排查 `episodes.jpg` 中标签错误的 Episode；它们的标签与 `tasks.xlsx` 的 `task_id` 列均不匹配。

> Why were the other 118 not delivered?  
> 为什么另外 118 条没有交付？

> Dig around for B-010, C-024 and C-025. Did they get labelled as something else? Did verlet do them?  
> 深入检查 B-010、C-024 和 C-025。它们是否被标成了其他名称？是否由 verlet 完成？

Claude 可以从每个 Episode 的 MCAP 中读取 Task 名称，因此能够判断 Episode 是缺失、重命名还是失败。仅查询数据库无法回答这个问题。也可以直接提供截图或电子表格进行分析。

### 媒体问题

> I think some of the Block manipulation episodes were overexposed. Inspect the L2 for good episodes, then pull the RAW back from the cloud.  
> 我怀疑部分 Block manipulation Episode 过曝。先检查 L2 找出正常 Episode，再从云端取回 RAW。

## 如何提出一个好问题

- **明确供应商、Task 和客户。**例如 `yun`、`Block manipulation`、`Luma`。不同供应商使用的 Task 名可能不同，否则 Claude 会要求补充信息。
- **明确所说的工时类型。**录制工时、交付工时和接受工时是三个不同数字，三者之间的差异通常最值得调查。
- **要求提供明细拆分，而不是单个数字。**这样才能得到可用于开票的表格，同时暴露卡住但尚未交付的 Episode。
- **结果看起来不对时要质疑。**例如：“I feel like this is still not right — isn't the subtask description in serial_number?” Claude 会重新检查，而不是坚持原答案。
- 任何将用于开票的结果，都要**要求展示查询语句**。

## 对答案做合理性检查

| 检查项 | 原因 |
| --- | --- |
| “Accepted” 不等于 “passed” | Luma 几乎没有将数据标记为 PASS，大多数已交付 Episode 仍是 PENDING。“Accepted”实际表示“尚未被拒绝”，该数字之后可能下降。 |
| 谁的 FAIL？ | 内部 Review 状态与客户结论是不同字段，而且经常不一致。“Not FAIL”含义不明确，必须说明是谁判定的。 |
| FAIL 和 DUPLICATE 默认排除 | 大多数交付统计默认排除这两类；如需计入，必须明确提出。 |
| 工时不足可能是配额导致 | 交付达到客户请求工时后会停止。认定数据缺失前，先检查 Customers 面板。 |

## 要求 Claude 修改内容时

- **批量或破坏性操作必须分阶段执行：**dry run → 小规模 canary → 完整执行。如果 Claude 没有主动提出，应明确要求，并仔细阅读 dry run 结果。
- **代码修复后必须重启服务。**Job 运行在 WebUI 进程中，只编辑文件不会立即生效。需要明确要求：“restart the webui so it picks up the fix”。
- **长时间任务要在后台运行。**重新上传和扫描可能持续数小时；Claude 会将其置于后台并汇报进度。可以关闭会话，之后使用 `/resume` 恢复。
