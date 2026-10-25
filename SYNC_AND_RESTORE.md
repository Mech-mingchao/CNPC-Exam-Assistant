# 私有仓库同步与恢复

本仓库保存用户明确授权私有备份的原始项目。保留初始化提交f40a3e0，不重写历史。题干、选项、原始答案、解析、来源与核验状态按字节保留；未重新分题、配答案或重建数据库。

## 新电脑首次下载

```powershell
git --version
git lfs version
git lfs install
git clone https://github.com/Mech-mingchao/CNPC-Exam-Assistant.git
cd CNPC-Exam-Assistant
git lfs pull
git lfs fsck
python scripts/verify_sync.py
```

私有仓库需要使用有访问权限的GitHub账号登录。不要将密码、访问令牌或API Key写入代码、命令文件或仓库。校验脚本只依赖Python 3.10及以上版本的标准库。

## 已有克隆更新

先处理自己的未提交更改，再执行：

```powershell
cd D:\CNPC-Exam-Assistant
git status
git pull --ff-only origin main
git lfs pull
git lfs fsck
python scripts/verify_sync.py
```

若遇到冲突、LFS下载失败或校验失败，停止使用该副本，不要强制推送、删除文件或重建数据库来绕过。`--ff-only`会在历史分叉时停止，保留本地及远程历史。

## 预期校验

- SQLite与JSONL均含10,663条唯一题目候选。
- 7,919条关联原始答案，5,455条关联原始解析。
- VERIFIED 2,575条，UNVERIFIED 8,073条，CONFLICT 15条；这些状态不会因同步而改变。
- 文件字节、数据库SHA256及完整题目记录摘要应与`reports/sync_integrity_manifest.json`一致。
- VERIFIED表示已有结构与来源核验，不等于所有答案客观正确。原项目质量限制继续适用。

Git LFS管理ZIP、PDF、SQLite、DB、JSONL及其他二进制资料。下载过程中需要足够的网络流量和磁盘空间。不要将此仓库或其中的第三方资料改为公开发布；本次授权仅针对用户自己的现有私有仓库备份，不构成再分发授权。

## 运行原有检索程序

原始脚本为保留来源而未修改，其中部分文件仍含原机器的绝对路径。另一台电脑先运行本页的独立校验脚本；使用检索功能时可安装`requirements.txt`后直接执行`python scripts/search_questions.py --query-file examples/query.json`。不要直接运行`rebuild.ps1`或资料提取脚本来替代已验证数据库。

原有`run.ps1`中的Python路径需要按新电脑环境另行配置；对副本作配置修改前保留已下载文件和校验结果。原始项目没有chat_history目录；新增memory/PROJECT_MEMORY.md只是有来源的项目事实摘要，不是聊天历史导出。
