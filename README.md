# 微信公众号文章索引 · 个人使用

输入公众号名称，获取 **文章标题、微信原文链接、发布时间和来源证据**。默认入口是 `crawl.py`，直接请求实时公开列表；不是只输出写死的样例链接，不需要微信登录、Cookie 或搜索 API 密钥。

## 已验证结果

2026-11-26，以 **郭磊宏观茶座** 实测：从公开列表取得 **200 篇**去重文章，均有微信原文 URL，且 URL 的 `__biz` 与目标账号一致。发布时间覆盖 **2026-03-27 至 2026-11-23（UTC）**。代码包含 **27 项自动化测试**，覆盖身份校验、分页异常、重复页、部分失败保留、链接清洗和导出安全。

**范围说明：**来源第一页报告收录478条、24页，但本次第11页返回空列表且把总数改为0。因此本项目只把已取得的200篇计入结果，不声称收录全部478篇，更不声称获得微信完整历史。程序会报告这种矛盾，不把空响应当作正常完成。微信原文当前可访问性没有逐篇验证，删除、地区限制、验证码等仍可能影响打开。

## 最快开始

需要 Python 3.10+；已在 Python 3.12 的 GitHub Actions 和本地 Python 3.13 执行测试。

```bash
git clone https://github.com/zizisaigao/wechat-officialAccount-reader.git
cd wechat-officialAccount-reader
python -m venv .venv
```

激活虚拟环境：macOS/Linux 使用 `source .venv/bin/activate`；Windows PowerShell 使用 `.venv\Scripts\Activate.ps1`。

```bash
python -m pip install -r requirements.txt

# 日常更新：来源按近期排序的第一页，最多20篇
python crawl.py "郭磊宏观茶座"

# 本次实测可用范围：前10页，最多200篇
python crawl.py "郭磊宏观茶座" --pages 10 --out output
```

打开 `output/index.html` 即可点击阅读；CSV 可导入表格软件；JSON 可继续供算法、检索或个人知识库处理。**直接在同一个输出目录重跑会去重累积，不会清空以前的文章。**不同公众号请使用不同 `--out` 目录。

### 不装本地环境

进入仓库 **Actions → Collect articles → Run workflow**，填写公众号名称和 `pages`，一般无需填写 `channel` 或 `seed_urls`。任务结束后在该次运行页面下载 `wechat-articles-运行ID` artifact。

该工作流只具有仓库读取权限，没有自动定时任务。artifact 保留14天。每次 Actions 运行使用干净目录，**不会自动合并前一次 artifact**；长期增量存档使用本地固定输出目录。日常手动运行默认1页；工作流自身变更触发的验收运行使用10页。

## 如何解决“公众号没有链接”

```text
公众号名称
  → 已核验映射 / 公开专栏名称匹配
  → 第三方公开列表分页
  → 校验 channel_id、公众号名称及已知 __biz
  → 保留真实微信文章 URL
  → 按 __biz + mid + idx 去重
  → JSON / CSV / HTML
```

已核验账号映射保存在 `accounts.json`。郭磊宏观茶座的 `__biz` 是 `MzI1NzAwODc3Nw==`，Reportify 专栏是 `S10740353838202886`。这些是公开标识，不是认证凭证。**知道账号标识并不足以生成文章链接**，真实文章的 mid、idx、sn 必须来自实际返回的数据。

未登记账号会尝试公开专栏名称精确匹配；不同名或同名歧义不会自动放宽匹配。名称无法解析时，使用 [`skills/wechat-reader/SKILL.md`](skills/wechat-reader/SKILL.md) 让具备联网搜索能力的 AI 找到真实专栏或文章候选，再提供已核验 `--channel`、`--biz`。不能保证任意公众号都被第三方收录。

## 输出字段与诊断

| 文件 | 内容 |
| --- | --- |
| `articles.json` | 本地累计的有效文章，包含 account、title、url、published_at、biz、source_url、verification、fetched_at |
| `articles.csv` | 同一批文章，UTF-8 BOM，并处理表格公式注入风险 |
| `index.html` | 可点击的静态文章列表，标题已转义，不加载外部脚本 |
| `run.json` | 本次抓取数、新增数、来源总数、分页范围、拒绝记录及错误 |
| `titles.json` | 详情兜底模式中尚待补齐链接的公开标题；正常列表模式为空数组 |

时间统一为UTC。`biz_match` 只证明返回链接中的账号标识一致，**不是原文内容或可访问性的担保**。

`source_total_count` 保留来源最初报告的数量；`source_last_total_count` 记录最后一次响应的数量。`verified_source_listing_complete=true` 只表示本次核验遍历了该第三方索引，不等于微信完整历史，所以 `complete_history` 始终为 false。

退出码：0=取得至少一篇有效文章；2=本次没有有效结果或致命错误；`--strict` 下，来源错误、身份拒绝或计数变化返回3，已经取得的结果仍保存。正常的页数预算截断不视为错误，但完整标记为false。

## 详情页与 AI Skill 兜底

`reader.py` 保留了另一条已验证路径：搜索引擎发现公开详情页 → 解析页面内 JSON / Next.js 序列化元数据 → 核验原文链接。这条路径可用于列表不可用、历史文章补充或新来源发现。

把真正找到的 `https://reportify.cn/social-media/数字ID` URL 写入 UTF-8 `candidate-urls.txt`，每行一条：

```bash
python reader.py "郭磊宏观茶座" --seeds candidate-urls.txt --limit 30 --out output
```

`accounts.json` 中4条 `seed_urls` 只是详情解析的回归样例，**不是实时文章目录**。默认主入口 `crawl.py` 不依赖它们。AI Skill 的搜索需要执行它的 AI 自带联网工具；Skill 文本自身不是搜索服务。详情解析暂不支持任意站点或直接微信页面作为输入。

## 实际尝试过的来源

以下是2026-11-26本次运行观察，不是对站点永久能力的判断。

| 来源 | 实测与取舍 |
| --- | --- |
| Reportify 公开列表 | 前10页取得200篇标题和微信原文URL；第11页返回矛盾空结果。作为当前主路径，记录覆盖范围。 |
| Reportify 公开详情页 | 无登录成功解析原文URL与账号名，4个回归样例通过。作为补充路径。 |
| 今天看啥专栏 | 匿名可见20条近期标题，文章链接受会员限制；只保存标题，不绕过。 |
| 瓦斯阅读归档 | 识别到账号及biz，但本次页面无可采集文章列表。 |
| FreeWeChat | 返回403，停止访问，不绕过。 |
| 搜狗微信 | 本次返回空响应，不能作为稳定数据入口。 |

旧工具 wechat-article-exporter 的作者于2026-07-30发布[停服说明](https://github.com/wechat-article/wechat-article-exporter/issues/200)，指出其依赖的微信核心接口关闭。因此这里没有照搬旧的 searchbiz/appmsgpublish 教程，也不声称所有微信接口都不可用。

当前使用的列表端点与参数来自 Reportify 自身公开网页客户端，并经过真实HTTP验证。这是第三方网页接口，**不是微信官方API，也不是承诺长期稳定的开放服务协议**；未来可能改变、限制或需要授权。

## 测试与维护

```bash
python -m unittest discover -s tests -v
```

主要文件：`crawl.py` 实时列表与名称解析；`reader.py` 详情解析、账号校验、网络限制、增量存档与导出；`accounts.json` 已验证映射；`tests/` 离线测试；`.github/workflows/collect.yml` 联网验收与手动运行；`skills/wechat-reader/SKILL.md` AI 发现和兜底流程。

仅采集个人需要的公开元数据，不保存全文。限制页数，默认请求间隔1.5秒；401/403/429、登录或验证码出现时停止对应来源，不换身份、不使用代理池、不绕过付费限制。不要提交Cookie、token、pass_ticket、HAR或浏览器状态；相关常见文件名已加入 `.gitignore`。

本项目不保证任何第三方网站长期可用，也不保证收录完整性。使用范围以来源允许的访问条件和实际可取得的数据为准。
