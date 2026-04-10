# Runtime Notes

## 固定实现

- Python 运行时：`3.10+`
- 向量模型：`text-embedding-v4`
- 向量维度：`1024`
- 可选重排模型：`qwen3-rerank`
- 根目录默认值：`/var/openclaw-kb`
- `topk` 与 `topN` 写入知识库自己的 `config.json`

## 目录结构

每个知识库目录位于：

- `/var/openclaw-kb/{kb}`

其中包含：

- `config.json`
- `manifest.json`
- `vectors.jsonl`
- `index.faiss`
- `{ts}-{safe_name}/`

每个文档目录包含：

- 原始文件
- 转换后的 `{safe_name}.md`
- `summary.txt`
- `chunks/chunk-00001.md`
- `t2q/00001-q-1.md`

## 索引规则

- `chunks/*.md` 作为真实召回单元
- `t2q/*.md` 作为召回代理单元
- 查询命中 `t2q` 时，必须反查到对应 `chunk`
- 最终输出只能返回真实 `chunk`
- 删除顺序固定为先执行 `delete --doc-id {ts}-{safe_name}`，再删除文档目录本身

## 查询流程

单知识库：

1. 将问题 embedding 成 1024 维
2. 查询 FAISS top `topk`
3. 若命中 T2Q，则折叠回真实 chunk
4. 去重
5. 若启用 `--rerank`，再按 `topN` 重排
6. 返回 Markdown

全知识库：

1. 对每个知识库执行同样的候选召回
2. 合并结果
3. 折叠回真实 chunk
4. 去重
5. 按需要执行 rerank
