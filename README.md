# bailian_faiss_kb

`bailian_faiss_kb` 是一个面向 OpenClaw 的技能，用于基于 Python、FAISS、MarkItDown 和阿里云百炼向量能力，构建并查询本地文件型知识库。

支持的能力包括：

- 将上传文件转换为 Markdown
- 基于 `chunks/` 和 `t2q/` 建立或刷新知识库索引
- 在文档删除后从索引中移除对应记录
- 对单个知识库或全部知识库执行语义检索
- 可选启用 `qwen3-rerank` 做结果重排

## 依赖组件

- Python `3.10+`
- `faiss-cpu`
- `markitdown[all]`
- `numpy`
- `requests`
- 百炼向量模型：`text-embedding-v4`
- 可选重排模型：`qwen3-rerank`

## 环境变量

推荐使用：

```bash
export BAILIAN_SK="你的百炼 API Key"
```

同时兼容历史变量名：

```bash
export BAILIAN-SK="你的百炼 API Key"
```

## 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

## 目录结构

默认知识库根目录：

```text
/var/openclaw-kb
```

每个知识库目录位于：

```text
/var/openclaw-kb/{kb}
```

每个文档目录位于：

```text
/var/openclaw-kb/{kb}/{ts}-{safe_name}
```

详细规则见：

- `references/layout.md`
- `references/content-rules.md`
- `references/runtime-notes.md`

## 常用命令

将文件转换为 Markdown：

```bash
python3 scripts/bailian_faiss_kb.py convert \
  --root-dir /var/openclaw-kb \
  --input /var/openclaw-kb/regulation/202604111230-demo/demo.docx \
  --output /var/openclaw-kb/regulation/202604111230-demo/demo.md
```

为单个文档目录建立索引：

```bash
python3 scripts/bailian_faiss_kb.py index \
  --root-dir /var/openclaw-kb \
  --kb regulation \
  --doc-dir /var/openclaw-kb/regulation/202604111230-demo
```

查询单个知识库：

```bash
python3 scripts/bailian_faiss_kb.py query \
  --root-dir /var/openclaw-kb \
  --kb regulation \
  --query "报销审批流程是什么"
```

查询全部知识库：

```bash
python3 scripts/bailian_faiss_kb.py query \
  --root-dir /var/openclaw-kb \
  --query "报销审批流程是什么"
```

启用重排查询：

```bash
python3 scripts/bailian_faiss_kb.py query \
  --root-dir /var/openclaw-kb \
  --kb regulation \
  --query "报销审批流程是什么" \
  --rerank
```

检查运行环境：

```bash
python3 scripts/bailian_faiss_kb.py doctor \
  --root-dir /var/openclaw-kb
```

## 安全说明

- 这个技能不会执行 shell 脚本，也不会下载远程安装脚本
- 它只读写本地知识库文件，以及命令中显式传入的输入输出路径
- 网络访问仅限阿里云百炼的 HTTPS embedding 和 rerank 接口
- 对外请求只会读取百炼 API Key，不会上传其他环境变量

## 发布说明

- 根目录 `README.md` 作为维护版本
- 发布到 ClawHub 时，再将这个文件拷贝到发布目录中

## 许可证

MIT，见 `LICENSE`。
