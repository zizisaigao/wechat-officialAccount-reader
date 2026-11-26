# 微信官方合集：不依赖 Reportify 的第二条采集路径

## 2026-11-26 实测：国泰海通政策和产业研究院

已成功读取微信官方「产业研究合集」首屏，取得10篇不重复文章的标题、原文URL和时间。合集页的账号显示名称与目标完全一致，10条文章URL的biz均一致。不是搜索结果拼接，也不是从其他国泰海通账号凑数。

- 微信 biz：`MzE5ODM1NDY2MA==`
- 微信原始标识：`gh_bf34d77f0f10`（合集页面cgiData.user_name）
- 合集 ID：`4434567390462525444`
- 合集名称：产业研究合集
- 页面显示总数：46；实际加载/导出：10；账号完整历史：否；合集已抓完整：否。
- [来源合集](https://mp.weixin.qq.com/mp/appmsgalbum?__biz=MzE5ODM1NDY2MA%3D%3D&action=getalbum&album_id=4434567390462525444)
- [真实联网运行](https://github.com/zizisaigao/wechat-officialAccount-reader/actions/runs/45755931207)
- 读取时刻：2026-11-26T04:33:18Z。原始合集HTML SHA256：`3520bc3c12d1a1ee5ebd6b4e56927948e8805fd1380af0f5def68d56c6470d0d`。

用户提供的文章带`cur_album_id`，因此可以将真实biz和合集ID组合成公开合集入口。合集页面HTTP 200且含账号名称和10条真实文章记录。随后尝试用户提供的单篇正文时跳转至验证码，程序停止该来源，没有绕过验证。结果解析使用同次成功响应保存的合集HTML，不再重复请求。

**这修正了此前“这个号没有跑通”的结论：官方合集路径现在已验证成功；Reportify专栏ID仍未知。** 原来的`examples/guotai-haitong-2026-11-26.validation.json`记录的是更早的Reportify与公开转载尝试，不能代表这次新路径的结果。

## 使用

```bash
python -m pip install -r requirements.txt
python album.py "国泰海通政策和产业研究院" --limit 10 --out output-guotai
```

`accounts.json`已保存经核验的合集映射。新账号也可提供自己的真实文章链接（必须含cur_album_id）或合集链接：

```bash
python album.py "公众号准确名称" --seed "真实文章或合集URL" --limit 10 --out output-album
```

输出`articles.json`、`articles.csv`、`index.html`、`run.json`。CSV带UTF-8 BOM并处理公式注入，HTML转义标题且不加载外部脚本。此入口输出当前页快照，不做旧结果累计；不同账号请使用不同目录。日期在导出文件中统一为UTC。

当前`album.py`仅解析合集第一页；`--limit`是输出上限，不会自动翻页。调大limit不等于得到全部46篇。缺少合集ID时不会猜测；账号名称、文章biz不一致或出现验证页时返回错误。只发一次合集请求，未实现自动重试，不获取全文。旧的`crawl.py`仍是Reportify入口；使用本账号的已验证路线请明确调用`album.py`。

离线回放保存的合集HTML：

```bash
python album.py "国泰海通政策和产业研究院" --html album-page.html --limit 10 --out output-guotai
python -m unittest discover -s tests -p test_album.py -v
```

新增9项合集单元测试在本地全部通过；覆盖文章seed转换、账号名/biz校验、去重、验证码页、凭证/域名限制、limit和覆盖范围。测试不访问网络。

## 本次取得的10条（日期已换算为北京时间UTC+8）

以下标题原样摘自合集元数据，不表示逐篇核验文章内容，也不保证每篇原文当前可打开。它们是该合集首屏按时间倒序的10篇，不能称为整个公众号的最新10篇。

| # | 日期 | 微信文章 |
| --- | --- | --- |
| 1 | 2026-11-17 | [【生物医药研究】中美细胞与基因治疗监管框架对比研究：创新与安全的平衡术](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247494633&idx=1&sn=4081eb581db32c7da995f1b6f64f031a&chksm=969e5862a1e9d1740bee59e81c89c6c2a9f8e8aca45d0057acf87d082081c61edb1cfdd83f3f) |
| 2 | 2026-11-16 | [【NextX科技半月观】第9期：全球首个化学遗传学神经调控临床研究发表](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247494289&idx=1&sn=a50fa17dbb38c2f8bbe744141f1f2a86&chksm=969e591aa1e9d00c58eba59c2e254871ed4d6b89d1758b37336c525b17570260d1dfb1149cf4) |
| 3 | 2026-11-02 | [【NextX科技半月观】第8期：OpenAI确认自研机器人，或重塑产业分工](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247494008&idx=1&sn=935e58130aaa31e7e4415e462871fc32&chksm=969e5af3a1e9d3e55bc5fa7c8eaaeecc1477a6a670a65b3ccbcc9bdb19cf664138dbc59f496e) |
| 4 | 2026-10-19 | [【NextX科技半月观】第7期：OpenAI批量生成数学手稿，验证筛选成瓶颈](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247493692&idx=1&sn=430eb825c83290fc23c775ab5cdaea2b&chksm=969e5bb7a1e9d2a1a18871efb2d9a495854cf35eb32e9bc407bc566f39cc920021cd63499425) |
| 5 | 2026-10-14 | [【生物医药研究】医药产业运行数据回顾和展望：复苏趋势初现，创新高景气延续](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247493287&idx=1&sn=dc9e582d0174b423b26741cfeda1ebdb&chksm=969e552ca1e9dc3a61993e7fc4546af1223dd670cf007bc7dc995da6323a114298ee770f9cd1) |
| 6 | 2026-09-28 | [【NextX科技半月观】第6期：多模态脑机接口迎突破，同步解码语音和手势](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247492164&idx=1&sn=26463f0220cf27f87aedc059c3ee5b45&chksm=969e51cfa1e9d8d90bc56633246ac791814e640f0319996974cd540891bae43daa286ef21058) |
| 7 | 2026-09-24 | [并购启新程，产业开新局—从中美周期对比、全球龙头实践看中国并购市场机遇](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247492055&idx=1&sn=c0590687fb6e5f8bf269f25996b9b278&chksm=969e525ca1e9db4a924c1bea4e4332af0ad498f31aed7d9329c331e824a56c39ef3094b48e4f) |
| 8 | 2026-09-21 | [【生物医药研究】中美创新药交易对比：结构分化，模式格局演进](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247491855&idx=1&sn=e33e0dfed35f20ad5e6583d993eb95cd&chksm=969e5284a1e9db92e8bf92516bf99dc74088ebb4cfe2cf9c8d9e40e1c098cf62496cfe28250b) |
| 9 | 2026-09-14 | [【NextX科技半月观】第5期：GPT-6 Astra发布，网络安全首达关键门槛](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247491116&idx=1&sn=7da7c72a51f68804fca923a809f58919&chksm=969dada7a1ea24b1b026802fbd2ed1876d3058ef97474989796ddfd4b67e91146a93e44a291f) |
| 10 | 2026-08-31 | [【NextX科技半月观】第4期：个体化肿瘤疫苗Ⅲ期成功，开启治疗新时代](https://mp.weixin.qq.com/s?__biz=MzE5ODM1NDY2MA%3D%3D&mid=2247490440&idx=1&sn=75c4b4e13e4cb88cad29816928ae9b5f&chksm=969da803a1ea2115bffee4eafe8729160bdf92128b0f164c8daed3d2eb112a1b2d5f42b87e45) |
