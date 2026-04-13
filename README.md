# bailian_faiss_kb

`bailian_faiss_kb` 是一个面向 OpenClaw 的技能，用于基于 Python、FAISS 和阿里云百炼向量能力，构建并查询本地文件型知识库。

支持的能力包括：

- 消费 OpenClaw 预先抽取好的文本文件
- 基于 `chunks/` 和 `t2q/` 建立或刷新知识库索引
- 对整个知识库执行全量重建，同时重建语义与 BM25 索引
- 在文档删除后从索引中移除对应记录
- 为指定知识库增加或删除保护词，并离线刷新 BM25 索引
- 对单个知识库或全部知识库执行综合、语义或关键词检索
- 可选启用 `qwen3-rerank` 做结果重排

## 依赖组件

- Python `3.10+`
- `faiss-cpu`
- `numpy`
- `requests`
- 百炼向量模型：`text-embedding-v4`
- 可选重排模型：`qwen3-rerank`

## 环境准备

本文档描述的是原生环境部署方式，不依赖 Docker。

下面的步骤以“你已经进入仓库根目录”为前提，也就是当前目录为：

```text
rag-kb/
```

如果你还没进入仓库目录，先执行：

macOS / Linux：

```bash
cd /path/to/rag-kb
```

Windows PowerShell / CMD：

```powershell
cd C:\path\to\rag-kb
```

仓库里的实际 skill 文件位于：

```text
src/bailian_faiss_kb/
```

### macOS

1. 安装 Python `3.10+`

如果你使用 Homebrew：

```bash
brew install python@3.12
python3 --version
```

2. 创建虚拟环境

以下 2、3、4 步都在仓库根目录 `rag-kb/` 下执行。

```bash
python3 -m venv .venv
```

3. 激活虚拟环境

```bash
source .venv/bin/activate
```

如果你就是在当前仓库 `/Users/ningwei/VSCodeProjects/rag-kb` 下操作，也可以直接用：

```bash
source /Users/ningwei/VSCodeProjects/rag-kb/.venv/bin/activate
```

4. 安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r src/bailian_faiss_kb/requirements.txt
```

5. 验证脚本可用

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /tmp/openclaw-kb doctor
```

### Linux

1. 安装 Python `3.10+`

Ubuntu / Debian 示例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

2. 创建虚拟环境

以下 2、3、4 步都在仓库根目录 `rag-kb/` 下执行。

```bash
python3 -m venv .venv
```

3. 激活虚拟环境

```bash
source .venv/bin/activate
```

4. 安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r src/bailian_faiss_kb/requirements.txt
```

5. 验证脚本可用

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /tmp/openclaw-kb doctor
```

### Windows

1. 安装 Python `3.10+`

如果你使用 `winget`：

```powershell
winget install Python.Python.3.12
py -3 --version
```

安装时建议勾选 “Add Python to PATH”。

2. 创建虚拟环境

以下 2、3、4 步都在仓库根目录 `rag-kb/` 下执行。

PowerShell：

```powershell
py -3 -m venv .venv
```

CMD：

```bat
py -3 -m venv .venv
```

3. 激活虚拟环境

PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

CMD：

```bat
.\.venv\Scripts\activate.bat
```

4. 安装依赖

PowerShell / CMD：

```powershell
python -m pip install --upgrade pip
python -m pip install -r src\bailian_faiss_kb\requirements.txt
```

5. 验证脚本可用

```powershell
python .\src\bailian_faiss_kb\scripts\bailian_faiss_kb.py --root-dir C:\temp\openclaw-kb doctor
```

### 验证通过的判断标准

执行 `doctor` 后会输出一段 JSON，至少应看到这些字段：

- `python_compatible: true`
- `requests: true`
- `numpy: true`
- `faiss: true`
- `jieba: true`

如果这些字段都正常，这个 skill 的 Python 脚本已经可以使用。

## 环境变量

推荐使用：

```bash
export BAILIAN_SK="你的百炼 API Key"
```

同时兼容历史变量名：

```bash
export BAILIAN-SK="你的百炼 API Key"
```

Windows 下可按当前 shell 设置：

PowerShell：

```powershell
$env:BAILIAN_SK = "你的百炼 API Key"
```

CMD：

```bat
set BAILIAN_SK=你的百炼 API Key
```

## 快速开始

```bash
source .venv/bin/activate
python -m pip install -r src/bailian_faiss_kb/requirements.txt
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /tmp/openclaw-kb doctor
```

进入这个工具之前，OpenClaw 必须先把原始文件抽取成文本，推荐保存为：

```text
/var/openclaw-kb/{kb}/{ts}-{safe_name}/{safe_name}.md
```

也兼容：

```text
/var/openclaw-kb/{kb}/{ts}-{safe_name}/{safe_name}.txt
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

每个知识库目录下还会维护：

```text
/var/openclaw-kb/{kb}/protected_terms.json
```

这个文件保存该知识库自己的保护词列表。增加或删除保护词后，脚本会基于现有 `vectors.jsonl` 离线重建 `bm25.json`，同时刷新 `manifest.json`，不需要重新做 embedding。

详细规则见：

- `src/bailian_faiss_kb/references/layout.md`
- `src/bailian_faiss_kb/references/content-rules.md`
- `src/bailian_faiss_kb/references/runtime-notes.md`

## 常用命令

为单个文档目录建立索引：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb index \
  --kb regulation \
  --doc-dir /var/openclaw-kb/regulation/202604111230-demo
```

重建整个知识库索引：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb rebuild \
  --kb regulation
```

为知识库增加保护词：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb protect-add \
  --kb regulation \
  --term 测试环境权限 \
  --term OpenClaw
```

从知识库删除保护词：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb protect-delete \
  --kb regulation \
  --term 测试环境权限
```

查询单个知识库：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb query \
  --kb regulation \
  --query "报销审批流程是什么"
```

只做关键词查询：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb query \
  --kb regulation \
  --query "报销审批流程是什么" \
  --retrieval-mode keyword
```

查询全部知识库：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb query \
  --query "报销审批流程是什么"
```

启用重排查询：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb query \
  --kb regulation \
  --query "报销审批流程是什么" \
  --rerank
```

检查运行环境：

```bash
python src/bailian_faiss_kb/scripts/bailian_faiss_kb.py --root-dir /var/openclaw-kb doctor
```

## 安全说明

- 这个技能不会执行 shell 脚本，也不会下载远程安装脚本
- 它只读写本地知识库文件，以及命令中显式传入的输入输出路径
- 它不负责原始文件到文本的转换；这一步必须由 OpenClaw 在进入流程前完成
- 网络访问仅限阿里云百炼的 HTTPS embedding 和 rerank 接口
- 对外请求只会读取百炼 API Key，不会上传其他环境变量

## 保护词说明

- 保护词按知识库存放在 `/var/openclaw-kb/{kb}/protected_terms.json`
- `protect-add` 和 `protect-delete` 只改当前知识库自己的保护词，不影响其他知识库
- 保护词会同时作用于 BM25 建索引和关键词查询分词
- 新增或删除保护词后，脚本会离线刷新当前知识库的 `bm25.json` 和 `manifest.json`
- 语义检索、向量文件和 `index.faiss` 不会因为保护词变更而重建

## 发布说明

- 根目录 `README.md` 作为维护版本
- 发布到 ClawHub 时，再将这个文件拷贝到发布目录中

## 许可证

MIT
