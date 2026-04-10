---
name: bailian_faiss_kb
description: 使用 Python、FAISS、MarkItDown、阿里云百炼 text-embedding-v4 与可选的 qwen3-rerank，维护基于文件目录的本地知识库；适用于文件转 Markdown、遍历 chunks 与 T2Q 建立索引，以及对指定知识库或全部知识库做语义查询。
metadata: {"openclaw":{"requires":{"bins":["python3"]},"primaryEnv":"BAILIAN_SK"}}
---

# 基于阿里云百炼和 FAISS 的知识库

这个 skill 用于配合 OpenClaw 自己的模型，维护目录化知识库。OpenClaw 负责保存原文件、生成摘要、做语义切片、生成 T2Q；Python 只负责文档转 Markdown、建立 FAISS 索引、执行查询。

## 适用场景

- 将上传文件转换为 Markdown
- 遍历某个知识库目录下的 `chunks/` 和 `t2q/` 建立或更新索引
- 在原始文档目录被删除后，从知识库级索引中移除对应数据
- 对指定知识库做语义查询
- 对全部知识库做语义查询

## 运行规则

- 先安装依赖：`python3 -m pip install -r {baseDir}/requirements.txt`
- 使用 Python `3.10+`
- 百炼密钥推荐使用环境变量 `BAILIAN_SK`；脚本同时兼容历史变量名 `BAILIAN-SK`
- 向量模型固定为 `text-embedding-v4`
- 向量维度固定为 `1024`
- 可选重排模型固定为 `qwen3-rerank`
- 配置项只有三个核心值：根目录、`topk`、`topN`
- `summary` 必须是单行纯文本，保存为 `summary.txt`
- T2Q 只作为召回代理，最终查询结果只能返回真实 chunk

## 安全边界

- 这个 skill 不执行 shell、不下载远程脚本、不启动后台服务、不监听端口
- Python 只读写知识库目录下的本地文件，以及脚本显式传入的输入/输出路径
- 只有 `index` 和 `query --rerank` / `query` 需要联网，且只会向阿里云百炼官方接口发起 HTTPS 请求：
  - `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings`
  - `https://dashscope.aliyuncs.com/compatible-api/v1/reranks`
- 只有百炼密钥会被读取并放入对应请求的 `Authorization` 请求头；脚本不会收集或上传其他环境变量
- `convert` 与 `doctor` 不依赖网络，也不会读取百炼密钥

## 先读路径规范

每次新增、处理、摘要、切片、T2Q、索引、删除之前，必须先读 [references/layout.md](./references/layout.md)。

主文档不再重复展开所有命名细节。执行时以 `layout.md` 为准。

## 再读内容格式规范

每次生成 `summary.txt`、`chunks/*.md`、`t2q/*.md` 之前，必须再读 [references/content-rules.md](./references/content-rules.md)。

主文档不再重复展开这三类内容的细节。执行时以 `content-rules.md` 为准。

## 路径最小约束

知识库根目录默认是 `/var/openclaw-kb`，但可通过 `--root-dir` 覆盖。

每次处理文件前，必须先算出这三个值：

- `kb`：知识库名，例如 `regulation`
- `ts`：上传时间戳，格式固定为 `yyyyMMddhhmm`
- `safe_name`：去掉危险字符后的文件基础名

只有先得到这三个值，后面的保存、转换、摘要、切片、T2Q、索引才能继续。

- 当前文档目录固定为：

```text
/var/openclaw-kb/{kb}/{ts}-{safe_name}
```

- 原始文件、`.md`、`summary.txt`、`chunks/`、`t2q/` 都必须放在这个目录下

## 职责拆分

### 1. 文件保存

这是纯 skill 步骤，不调用 Python。

OpenClaw 需要：

- 先按 [references/layout.md](./references/layout.md) 算出目标目录和目标文件名
- 创建目录 `/var/openclaw-kb/{kb}/{ts}-{safe_name}/`
- 保存原文件到 `/var/openclaw-kb/{kb}/{ts}-{safe_name}/{safe_name}{ext}`

### 2. 文件处理

这一步调用 Python，把原文件转成 Markdown：

```bash
python3 {baseDir}/scripts/bailian_faiss_kb.py convert \
  --root-dir /var/openclaw-kb \
  --input /var/openclaw-kb/regulation/{ts}-xx/xx.docx \
  --output /var/openclaw-kb/regulation/{ts}-xx/xx.md
```

### 3. 摘要

这是纯 skill 步骤，不调用 Python。

OpenClaw 读取 `xx.md` 后，需要：

- 先读 [references/content-rules.md](./references/content-rules.md)
- 按规则生成 `summary.txt`
- 保存到当前文档目录里的 `summary.txt`

### 4. 切片

这是纯 skill 步骤，不调用 Python。

OpenClaw 读取 `xx.md` 后，需要：

- 按语义切分正文
- 每个切片输出为单独的 Markdown 文件
- 先读 [references/content-rules.md](./references/content-rules.md)
- 文件名和保存目录必须遵守 [references/layout.md](./references/layout.md)

### 5. T2Q

这是纯 skill 步骤，不调用 Python。

OpenClaw 需要：

- 针对每个 chunk 生成问题
- 每个问题单独存一个 Markdown 文件
- 先读 [references/content-rules.md](./references/content-rules.md)
- 文件名和保存目录必须遵守 [references/layout.md](./references/layout.md)

### 6. 建立索引

这一步调用 Python。它会遍历一个文档目录下的 `chunks/` 和 `t2q/`，将内容 embedding 后写入知识库级索引。

```bash
python3 {baseDir}/scripts/bailian_faiss_kb.py index \
  --root-dir /var/openclaw-kb \
  --kb regulation \
  --doc-dir /var/openclaw-kb/regulation/{ts}-xx \
  --topk 10 \
  --topN 10
```

行为：

- 遍历 `chunks/*.md`
- 遍历 `t2q/*.md`
- 用 `text-embedding-v4` 生成 1024 维向量
- 将 chunk 与 T2Q 代理一起写入 `vectors.jsonl`
- 更新 `index.faiss`
- 更新 `manifest.json`
- 将 `topk` 与 `topN` 写入知识库配置

### 7. 删除

删除分成两步，而且顺序固定为先删索引，再删文件：

1. 先调 Python 删除知识库索引中的对应数据并持久化：

```bash
python3 {baseDir}/scripts/bailian_faiss_kb.py delete \
  --root-dir /var/openclaw-kb \
  --kb regulation \
  --doc-id {ts}-xx
```

行为：

- 从 `vectors.jsonl` 中删除该文档对应的 chunk 和 T2Q 向量记录
- 重写 `index.faiss`
- 重写 `manifest.json`

2. 再由 OpenClaw 删除整个文档目录：

```text
/var/openclaw-kb/regulation/{ts}-xx
```

### 8. 查询

这一步调用 Python。

查指定知识库：

```bash
python3 {baseDir}/scripts/bailian_faiss_kb.py query \
  --root-dir /var/openclaw-kb \
  --kb regulation \
  --query "报销审批流程是什么"
```

查全部知识库：

```bash
python3 {baseDir}/scripts/bailian_faiss_kb.py query \
  --root-dir /var/openclaw-kb \
  --query "报销审批流程是什么"
```

需要更高精度时，显式启用 rerank：

```bash
python3 {baseDir}/scripts/bailian_faiss_kb.py query \
  --root-dir /var/openclaw-kb \
  --kb regulation \
  --query "报销审批流程是什么" \
  --rerank
```

查询规则：

- 若指定 `--kb regulation`，只查询该知识库
- 若未指定 `--kb`，遍历根目录下所有知识库
- 若知识库索引未加载，则从文件中加载
- 无 rerank 时，按 `topk` 做 FAISS 召回，再按 `topN` 返回
- 有 rerank 时，先召回候选，再去重到真实 chunk，最后 rerank 返回前 `topN`
- 命中 `t2q` 时，必须反查回真实 chunk

## 查询输出格式

默认返回 Markdown，按文件分组，每个命中的 chunk 单独成节。

格式固定为：

```md
## xx.docx

- uploaded at {ts}
- summary: 摘要文本
- total chunks: 该文件的切片数量

### Chunk 00001

这里是 chunk 内容

### Chunk 00002

这里是 chunk 内容
```

注意：

- `summary` 来自 `summary.txt`
- 只能返回真实 chunk 内容，不能返回生成的问题文本

## 检查运行环境

```bash
python3 {baseDir}/scripts/bailian_faiss_kb.py doctor \
  --root-dir /var/openclaw-kb
```

## 操作说明

- 这个 skill 不负责替 OpenClaw 生成摘要、切片或 T2Q 的内容，只负责规范这些文件应该长成什么样，以及如何调用 Python
- 如果某个 chunk 文件或 T2Q 文件命名不合法，Python 会拒绝索引
- 如果 `summary.txt` 超过 200 字，Python 会拒绝索引
- 需要更详细的实现说明时，读取 [references/runtime-notes.md](./references/runtime-notes.md)
