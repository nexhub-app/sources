# 短剧/影视 API 站适配的本质规律（源无关）

从多个短剧聚合应用的 native 基准实现与多站适配实战中提炼（2026-11）。**本文不点名任何真实站点**——端点、参数、密钥等以各站的基准实现为准，这里只沉淀引擎与协议层的可迁移规律。写短剧/影视源前先按 §0 分型，再按对应章节规避坑位。

## 0. 站点分型速查（按协议形态）

| 类型 | 特征 | 路线 | 落点 |
|---|---|---|---|
| 纯 JSON API | GET/POST + 查询参数，无签名 | 声明式 jsonpath 或 `script` | field-spec §3-5 |
| 固定密钥签名 | 参数按字典序拼串 + 常量密钥求哈希 | `script`，每请求现算 | §2 |
| 登录换 token | 匿名设备登录 → token 缓存复用 | `script` + `context.storage` | §2.4 |
| 响应加密 | Base64+AES，密钥可从请求推导 | `script` + `context.crypto` | §2.3、§3 |
| 网页 SSR + 内嵌 JSON | HTML 里有框架注入的 JSON（`_ROUTER_DATA` / `__NEXT_DATA__`）或播放器配置对象（`player_aaaa`） | `script` 正则/括号配对抽取 | §5 |
| CF/验证墙 | 直连 403、返回几百字节质询页 | `webview-html`，用户手动过一次 | SKILL.md 硬规则 14 |

## 1. 引擎事实（实测修正旧文档）

1. **入口函数一律同步**；`await`/`.then` 仅限脚本内部与 `__processor`。async 入口在引擎层有三策略降级链（Promise 引用 → async IIFE 重跑 + handlePromise → .then 轮询）：flutter_js 的 FFI QuickJS 把挂起 JS Promise 包成 **pending Dart Future**（`isPromise` 恒 false，stringResult 是 Future 的 toString——`"Instance of 'Future<dynamic>'"`），引擎已修为识别该形态转 `handlePromise`（await rawResult + 20ms 泵 job 队列），桌面端实证 async 入口可落地；但那是三档降级链，真机/鸿蒙桥语义未验，**签名站不要赌，md5 等签名一律内嵌纯 JS 同步现算**（见 §2.5）。拿到二次请求数据仍优先 `__meta`（少一层异步，更稳）。
2. **`context.crypto.aesEcb/aesCbc` 的 key/data/iv 一律按 `encoding` 参数解码**（`base64` 或 `hex`），不是原始字符串！要传「16 字节 ASCII 密钥」需先 `btoa(key16)`。解密返回 utf8 字符串；ECB/CBC 均自带 PKCS7 填充。
3. **`btoa`/`atob` 沙箱有宽松 polyfill**（>0xFF 码位截断）：全 ASCII payload 放心用；任意字节串转 base64 用 `String.fromCharCode` 循环 + `btoa`。
4. **`__meta` 链上限 4 跳**（每一跳都计入，含第一个 meta）。预取失败非致命（raw=''，脚本仍执行）——所以「脚本端点 + 哑路由 `/`」是合法形态：脚本完全自取数据。
5. `__fetchResponseType: 'text'` 让预取返回原始文本。三种场景必需：加密响应、内嵌 JSON 的 HTML、**大整数 JSON**（§3）。
6. **处理器首参形态要看清**：单条 meta 预取的处理器收到 `[data, headers]` JSON 数组（headers 供提取响应头凭证/令牌），批量 meta 才是裸响应列表。明确知道是单条跳的处理器用 `Array.isArray(raw) ? raw[0] : raw` 归一化——批量场景的响应体本就可能是数组，盲目归一化会吞掉批量数据。

## 2. 签名/加密四套路（形态学）

### 2.1 拼串签名
参数按**字典序** `k=v` 拼接 + 常量密钥 → md5/hex。两个高频坑：
- URL 上的参数签名与请求头里的凭证签名是**两套**，漏带头的症状是「请求 200 但内容为空/形状不对」——把「算头」封成统一 helper（如 `mgMeta(context, url, processor)`），所有端点走它。
- 签名串里的查询词用**原文**（不转义），URL 里才转义——两处口径不同。

### 2.2 时间戳指纹
`md5(毫秒时间戳字符串的后 10 位)` 之类，每次请求现算，拼在 query 上。

### 2.3 URI 推导密钥
响应 = Base64(AES-128-ECB(JSON))，**密钥 = 实际发出的 URI（path+query）前 16 字节**。脚本拼 URI 时暂存（模块级变量跨 `__processor` 可读），解密用同一字符串推导密钥——天然自洽，参数顺序随意但必须与所发 URI 逐字一致。响应 base64 可能缺 padding：先去空白再补 `=` 到 4 的倍数。

### 2.4 设备指纹与登录 token
- 设备指纹类请求头：固定设备信息 JSON → base64 → **逐字符过映射表**（本质是 base64 字母表置换）→ 拼串求 md5 作头签名。密钥/映射表/设备串属于站点机密，只写在源 JSON 里。
- 匿名登录换 token：`context.storage` 缓存 `{t, ts}`，带 TTL（基准缓存时长留 10% 余量），登录请求**加重试**（首跑抖动实测会失败一次）。

### 2.5 签名同步化：内嵌纯 JS 哈希
签名每请求现算 + 入口必须同步 ⇒ `context.crypto.md5`（异步桥）用不了 ⇒ **脚本内嵌纯 JS md5**（~2.5KB，RFC 1321，UTF-8 手工编码以兼容无 `unescape` 的沙箱）。写对它的两个铁坑：

- **两半加法的进位**：`add(x,y)` 的高 16 位必须含 `(x>>16)+(y>>16)+(l>>16)` 三项——漏掉任一项症状是「输出每条都错、且不同输入的错法有公共后缀（最高寄存器近似不动）」，结构看起来完全正常。对拍是唯一防线。
- **常量表与对拍**：64 轮常量手抄必错，用脚本按 `floor(|sin(i+1)|·2^32)` 生成或直接 hashlib 对拍；对拍集必须覆盖**空串、纯 ASCII、真实签名串、中文、emoji**（代理对路径独立出错的成本极高）。

```js
// 签名处直接同步调用；URL 参数签名与头签名共用同一个内嵌实现
var sign = md5('k=v&…' + KEY);   // 签名串里的查询词用原文，URL 里才转义
```

配套模式（每请求现算签名 + 入口同步）：

```js
function meta(context, url, processor) {
  var q = deviceParams();                       // 现算设备指纹
  return { __meta: true, __fetchUrl: url,
    __fetchHeaders: { 'sign': md5(authPrefix + q + KEY), /* … */ },
    __fetchResponseType: 'json', __processor: processor };
}
function parseList(raw, context) {
  var p = Number((context && context.page) || 1);
  return meta(context, base(context) + '/list?page=' + p + '&sign=' + md5('page=' + p + KEY), 'pickList');
}
```

**选集存「接口 + #ep=集号」且签名每请求现算的站**：点播入口必须从存储 URL 抽出业务参数**补算签名**再发（选集落库时签名是旧的，且不含在 URL 里）——否则点播恒「验签失败」。抽参用 `url.match(/param_id=([^&#]+)/)`。

## 3. 大整数 ID 精度陷阱（>2^53）

17~19 位数字 ID（如 7701935931787316286）超过 JS float64 安全整数（2^53≈9e15）：`JSON.parse` 后**静默**变 `...316000`，详情/播放全部串台。**宿主侧解析再传进 JS 也一样丢**（序列化链路是 JSON→Number）。

修法：解析前对 JSON **文本**做定向加引号，把大数字变字符串再 parse：

```js
// 定向键（安全、不误伤字符串内容）
text = text.replace(/("series_id")\s*:\s*(\d{15,})/g, '$1:"$2"');
// 数组形态：值可能本就是字符串数组，别二次加引号！
text = text.replace(/("vid_list"\s*:\s*\[)([^\]]*)(\])/g, function (all, head, inner, tail) {
  return head + inner.replace(/"(\d{15,})"|(\d{15,})/g, '"$1$2"') + tail;
});
```

配套：相关路由 `responseType: 'text'`，脚本自己 parse（避免宿主先 parse 丢精度）。校验手段：冒烟后比对 firstId 与源站原值**逐位一致**。

## 4. POST 体里的中文与 Content-Type

- 部分站方后端只接受 `\uXXXX` 转义的 JSON 体，原生 UTF-8 中文一律 500。统一转义：

```js
function asciiEscape(text) {
  return String(text == null ? '' : text).replace(/[\u0080-\uffff]/g, function (ch) {
    var hex = ch.charCodeAt(0).toString(16);
    while (hex.length < 4) hex = '0' + hex;
    return '\\u' + hex;
  });
}
// 手工拼 body：'"' + key + '":"' + asciiEscape(value) + '"'
```

- 排查口诀：POST JSON 带 500 → **二分字段**（空值 OK、中文值 500 → 就是它）。注意宿主/Node 默认 `Content-Type: text/plain`，脚本 POST JSON **必须显式带 `application/json`**，否则服务端按文本处理直接报错。
- 基准实现同样会踩这两坑（原生 UTF-8 序列化、缺 Content-Type），「基准 README 说接口返回空数据」≠ 接口真坏——先按本节自查。

## 5. 内嵌 JSON 抽取（框架注入数据）

- 用**花括号配对法**取完整 JSON（`JSON.parse` 容不下尾随的 `;</script>`）：定位键名 → 第一个 `{` → 计数配对（处理字符串与转义）→ parse 切片。
- react-router/Next 类框架的 loaderData 键名带占位符（`category_$`、`player_(series_id)/(vid)/page`）——按**前缀匹配**取第一个非空对象，别写死键名。
- 播放页可能出现 `protectedPlayback: true` 且无直链（VIP/未登录集）——按空产出处理并走下一兜底，不要假装能解。

## 6. 时效直链与 #ep= 模式

分集里出现「带时效签名的直链」（X-Amz-Expires、sign+t 等）或「解析服务的内部分集 ID」时，一律存 `接口地址 + '#ep='(或'#jx=') + 集标识`，点播时由 video 脚本现取。理由：

- 存直链会过期（403）；存解析 ID 时，video 路由预取会跟随 302/直链把整个视频拉下来（实测 32MB/集）。
- HTTP 客户端按规范丢弃 `#fragment`，所以路由 `{url}` 预取的自然就是接口响应本体，脚本直接从 raw 里挑集。
- 稳定的 302 跳转地址（每集固定入口）也走此模式，播放器自行跟随跳转。
- 解析服务换直链的候选常为「双域名 × 双脚本」共 4 个——恰好用满 `__meta` 4 跳：processor 校验失败就返回下一个 meta 描述符。

## 7. 引擎能力边界（遇到即放弃）

沙箱**没有 gzip，也没有二进制 POST 体**（字符串 body 经 UTF-8 编码会破坏 >0x7F 的字节）。所以「请求体先 gzip 压缩再 AES 加密、Content-Type: octet-stream」这类协议**超出源 JSON 能力边界**——判定法：看基准实现的请求体是否先压缩、Content-Type 是否 octet-stream。遇到就放弃并在结论里注明原因，不要硬做。

## 8. 站点存活判定（短剧站特别版）

- API 主机根路径 404/503 ≠ 站死（API 型主机根路径不服务是常态）——要打**真实业务端点**再判。
- 「列表活、详情死」的站按基准照建源，description 写明故障点与日期，站方恢复即自愈；解析域名 DNS 已注销的大概率不会复活。
- 聚合应用 README 的「待验证」行常常是它自己的 bug（见 §4），不要照抄结论，要实测。

## 9. 移动端 UA 门禁

桌面 UA 403 / 移动 UA 200 的站不少见——先双 UA 探测再定路线；命中时 `antiHotlinking.userAgent` 指定移动 UA，列表/详情/播放全链路同 UA。

## 10. 翻页 URL 槽位（筛选型目录 URL 的页码位置）

MacCMS 系 `/show/` 目录 URL 是**多槽位**结构（`{id}-...-{page}-...-{尾参}`），页码只有一个固定槽位，其余槽是站点自己的筛选位。高频翻车：

- **页码填错槽**：把 `{page}` 写进「看起来像页码」的槽位（常是**尾槽**）——尾槽多为惰性回显（改它的值内容不变）或缺了直接 404，而真页码槽留空 → 恒出第 1 页。症状：`page=2/3/8` 返回完全相同的条目。
- **整段缺 {page} 占位符**：同上，永远第 1 页。
- **尾槽是必填的**：镜像站点自己的分页链接（含尾参）最稳；自造「更简洁」的 URL 常直接 404。

判定法（不猜）：

1. 抓第 1 页 HTML，找分页组件里「第 2 页/下一页」的**真实 href**，逐槽位对齐（按 `-` split 数字段位置），镜像整条 URL 形态，只把页码换成 `{page}`。
2. 修完自检：**page=2 与 page=1 的条目 id 集合必须零重叠**；分类页同理（带筛选词翻页）。
3. 站点可能对同一 URL 模板的不同筛选形态使用不同槽位（无词版与带词版的页码槽前破折号数不同）——两种形态各自的分页链接分别验证，不要想当然统一。

## 11. 免验证搜索：优先站方联想接口

短剧/影视站的 HTML 搜索页是**人机验证高发区**（图形码/滑块整页墙）。在写 `webview-html` 搜索之前，先探测站方自带的**搜索联想 JSON 接口**（MacCMS 形态：`/index.php/ajax/suggest?mid=1&wd={关键词}&limit=50`）：

- 返回 `{list:[{id,name,pic,...}]}`，按名称模糊匹配，**通常不挂验证墙**（它就是站内搜索框自动补全用的）。
- 源侧写法：搜索路由 `responseType: json` + override `builtin` + 选择器 `$.list / $.id / $.name / $.pic`。`page` 参数多数无效（联想接口不分页，`limit` 上限即结果上限，够用）。
- 仓库先例：同形态 MacCMS 源已用此路线稳定运行（见 `ls plugins/builtin/`）。

**为什么别依赖 webview-html 人肉过验证**：App 的验证检测器只认已知特征（Cloudflare、`_guard/*.js`、MacCMS `mx-mac_msg_jump` 弹窗等）。站点**自制验证页**（自定义 slider/图形码表单）不在特征库里 → HTML 被当正常内容解析 → 0 条且**永远不弹验证入口**，用户死路。webview-html 只适合「检测器认得出」的墙；有免验证 JSON 接口时，JSON 永远优先（对齐铁律 2「能直连就不开 WebView」）。

## 12. 多线路剧集：用 lineList 分组，别扁平混名

MacCMS 站常见多播放线路（同内容多 CDN：pills/tab 切换、`hl-tabs` 等）。把各线路锚点写进同一个扁平 `list` 的后果：同名剧集重复出现（如两条「全集」）、用户点到失效 CDN 的那条就报错，且无从切换——被感知为「播放坏了」。

引擎原生支持线路分组，episodes 选择器三件套：

```json
{
  "lineList": "//容器根/每线路的包裹元素",
  "lineName": "//线路标题选择器（与容器同序的平行列表）",
  "list": "容器内的剧集锚点（CSS 即可）"
}
```

规则与坑：

- `lineName` 是对**整页**求值的平行选择器，必须与 `lineList` 容器**逐个对齐**。tab 导航里常有「无 href 的占位项」（如『播放列表』按钮，`href="#"`）——用 `starts-with(@href,'#面板前缀')` 之类谓词滤掉，否则名字错位、张冠李戴。
- 容器选择器别用会误伤导航锚点的宽匹配（`[id^=pills-]` 会连导航 `<a>` 一起抓）；限定在面板容器**直接子级**。
- 容器解析为空时引擎自动回退扁平模式，不会整源空剧集——放心上分组。
- 线路名会写进 `Episode.lineName` 供 UI 分组展示；线路 = 同内容的备用 CDN，是 CDN 抖动时用户自救的入口。

## 13. CDN 直链验证：master 能开 ≠ 能播

- 播放列表主机与**分片主机常是两个域名**（variant/segment 指向另一家 CDN）。只验 master（往往仅百字节）不算数——要顺着 master→variant→segment 链把分片也打一次。
- 部分 CDN 对**新建连接**间歇断连（RemoteDisconnected/403，实测可达一成上下），而 **keep-alive 长连接稳定**——curl 单发成功有运气成分。验证分片可靠性要同连接连打多次；播放器（mpv）正是长连接形态，单发失败别急着判死。
- 分片 host 403 别急着重写 host：播放列表主机多半不服务分片（跨主机重写前先实测）。

## 14. 交付自检清单（短剧源追加项）

- [ ] 大整数 ID 冒烟：firstId 与源站逐位一致（§3）
- [ ] 中文搜索词实测过（§4 两类坑都可能在这暴露）
- [ ] POST 头 Content-Type 显式声明（§4）
- [ ] 每请求的签名头都走了统一 helper（漏头=全空，且只空不报错，§2.1）
- [ ] 入口已同步化：签名用内嵌纯 JS 哈希且经 hashlib 对拍（空串/中文/emoji 向量齐，§2.5）；若保留 async 入口，桌面探针必须实证 Phase3 落地
- [ ] 单条 meta 处理器已归一化 `[data, headers]` 形态（§1.6）
- [ ] 选集存「接口+#ep」且签名现算时，点播入口已从 URL 抽参补算签名（§2.5）
- [ ] 加密响应的 base64 padding 容错（§2.3）
- [ ] 播放端点第一跳不落在时效直链/大文件上（§6）
- [ ] 协议若含 gzip/二进制体 → 已放弃并注明（§7）
- [ ] 翻页自检：page=2 与 page=1 条目 id 集合零重叠（latest 与分类各验一次，§10）
- [ ] 搜索已优先联想 JSON 接口；若走 webview-html，确认验证页是检测器已知特征（§11）
- [ ] 多线路用 lineList 分组且 lineName 与容器对齐（无占位 tab 混入，§12）
- [ ] 播放验证打过 master→variant→segment 全链，分片同连接多次（§13）
- [ ] 分类「不全」已查筛选面板维度；filters 块用 `{param?}` 语法且翻页/去参自检过（§15）
- [ ] 「不清晰」按三分法排除过：分片码率实测、签名对照、抽样定素材上限（§16）

## 15. 分类「不全」先看筛选面板：nav 一个类型 ≠ 维度只有一种

症状：App 分类栏只有一个 Tab，用户报「分类不全」。先别急着猜别的 type id——很多站导航本来就只有一个类型，**完整浏览维度在分类页的筛选面板**（容器 class 常含 `screen`/`type-slide`：按分类/按年份/按地区/按排序），数据走 `search.html?searchtype=5&tid=X&year=Y&area=Z&page=N` 这类**与搜索共用路由的查询串**，而非独立目录页。

判定法（不猜）：

1. 抓分类页，把筛选面板每组 `<li>` 全量列出。**「全部」项的 href 就是去参基线**：其余项与基线的 diff 即该维度的参数名与值域。
2. 播放页/详情页的属性链接（地区/年份）常把同一维度再暴露一次，交叉验证值域。**值域只剩一个的维度不值得做成筛选组**（单选项组是噪音）。
3. 导航上的演员名/明星词多是 `searchtype=1`（按演员搜）——那是搜索词，不是分类维度，别搬进分类体系。

修法（App 原生筛选面板，别把年份做成 15 个分类 Tab）：

- `routes.category` 改指筛选接口：`/search.html?page={page}&searchtype=5&tid={category}&year={year?}&order={order?}`；
- `filters` 块声明分组：`param` 对应路由占位符；`{param?}` 可选语法=值为空或键缺席时整段移除该参数（不留 `year=` 空段）；中文值引擎自动 encodeComponent；
- 自检三件套：①去参基线 URL 与带参 URL 都出完整列表；②page=1/page=2 条目 id 集合零重叠（§10 同款）；③新列表与旧分类页同一套卡片标记时 selectors 零改动；
- 排序维度可顺手做 homeSection：复用 category 路由 + `params: {category, order}` 固定参（板块的「查看全部」会落到分类 Tab，用户在筛选面板一步就能再选同维度，自洽）。

## 16. 「视频不清晰」三分法：路径标签、签名、素材上限

用户报「不清晰」时按顺序排除三层，别一上来改取址脚本：

1. **路径标签会骗人**。m3u8 路径里的 `/1080/` `/720/` 只是站点目录名，与真实码率无关（实测同站「1080」档分片仅 400~900kb，「720」档 542kb）。真相在 playlist 里：media playlist 数**分片子目录的码率名**（`904kb/xxx.ts`）、master playlist 看 `RESOLUTION=`/`BANDWIDTH=`。探针脚本：`scripts/probe_play_quality.py`（页址→明文直链→playlist 真相一条龙）。
2. **签名不改变供给**。播放器 iframe 常把直链再包一层带 `sign`/`t` 的跳转页（`publicApi.php?code=vip&url=…` 形态）。判定：同 URL 带签/不带签各取一个分片，**字节数一致**即签名与画质无关（顺带证明分片层无防盗链）。跳转壳页若只是广告 iframe（页面上没有第二个直链），也是死路一条，别追。
3. **素材本身就是上限**。抽样多部剧的播放页：若每部都只有一条线路、每集页只有一个明文地址、且站方网页播放器播的就是同一 URL——App 与站方画质必然一致，「不清晰」= 站方转码码率低，**源侧无解，如实告知，别硬修**（改了也是安慰剂）。

源侧唯一能做的是**防御性择优**：取址脚本别再「取第一个匹配」——收集页面全部 m3u8/mp4 明文候选（排除播放器壳路径），按**分辨率标签降序 + m3u8 优先**排序取第一。单候选时行为不变；站点未来在同页埋多档地址时自动选最优。

### 探测节奏（配套）

同站连发请求会吃 **502「服务暂时不可用」限流页**（与 URL 本身无关）：探站间隔 3~5s、带完整浏览器头+referer+cookie。用**对照实验**区分两种 502：普通分类页 200 而目标 URL 502 → 目标接口需要完整头/会话；全站都 502 → 触发限流，歇一会儿再测。
