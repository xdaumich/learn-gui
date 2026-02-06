帮我搞个方案吧, 我需要一个网页 app, 用 webrtc 看相机数据, 然后 rerun web viewer 看轨迹  

下面给你一个能落地的整体方案：一个网页 App，左边 WebRTC 低延迟看相机，右边 嵌入 Rerun Web Viewer 看轨迹/姿态/点云/TF，并且把两边用统一时间轴对齐。



目标效果（你打开一个 URL）





Video 面板：WebRTC 

 实时播放（超低延迟）



Rerun 面板：网页里嵌入 Rerun Web Viewer（不是开 native app）



同步：拖动时间轴时，轨迹和视频尽量对齐；实时播放时也对齐

Rerun Web Viewer 支持网页嵌入（iframe 或 JS 包） 

并且可以通过网络把 log 数据喂给 Web Viewer（官方有 serve 示例） 



架构（推荐版本：1 个后端 + 1 个网页）

1) 数据路径

相机视频（WebRTC media）





Camera ->（H264 硬件编码）-> WebRTC Publisher -> Browser 



轨迹/传感器（Rerun data）





Robot/Estimator ->（protobuf/json）-> Backend ingestion



Backend 用 Rerun SDK 记录（log）-> Rerun Web Viewer 通过 WebSocket 接收并展示



Rerun Web Viewer 在浏览器跑 Wasm，有内存/性能上限（2GiB、单线程等），所以“实时 + 回放”建议做窗口化/抽稀 

2) 控制/同步路径





Browser ->（WebSocket 或 WebRTC DataChannel）-> Backend：发送“当前播放时间 t / pause / rate”



Backend：





给 Rerun：设置时间轴（按同一时间基准记录）



给 Video：通过 DataChannel 下发“目标时间/对齐信息”（可选）



组件选型（我给你一个“最小能跑”组合）

前端（Web App）





Vite + React（或纯 JS）



WebRTC 播放：原生 RTCPeerConnection + 





Rerun Viewer 嵌入：





推荐：@rerun-io/web-viewer-react 或框架无关的 @rerun-io/web-viewer 



也可以先用 iframe 嵌入（更省事）

 

UI 布局建议：





左右分屏（Video / Rerun）



顶部一排按钮：Connect / Record / Pause / Live



底部：统一时间轴（或直接用 Rerun 自带时间轴 + 旁边显示 video 的当前 pts）

后端（强烈推荐先做一个“汇聚后端”）





FastAPI（HTTP + WebSocket）



WebRTC：





LAN 内点对点：aiortc（最简单）



多人看/更稳：上 SFU（mediasoup / ion-sfu）——第二阶段再上



Rerun：





后端用 Rerun SDK 记录轨迹、TF、点云、图像元数据



然后用官方的“serve + web viewer”模式把数据推到浏览器 
（你也可以把 viewer 嵌进自己的网页里）



时间同步（关键点：

统一 timebase

）

你最终想要的是：video 帧时间戳和轨迹时间戳在同一坐标系里。

最稳的做法（推荐）





Robot/Camera 机器跑 PTP（IEEE1588） 或至少 NTP，统一系统时间（wall clock）



每条轨迹消息带 t_ns（Unix monotonic 或 realtime，但要统一）



每个视频帧也有采集时间 t_capture_ns（在 publisher 侧打进去）

WebRTC 里的现实问题





浏览器 

 给你的通常是播放端的 currentTime（渲染时间），不是原始采集时间



所以要做对齐，通常需要旁路时间戳通道：

推荐实现：WebRTC DataChannel 发“帧时间戳映射”





publisher 每隔 N 帧发送：{frame_id, t_capture_ns, rtp_timestamp} 或 {t_capture_ns, seq}



browser 收到后，用估计出来的 offset 把“当前播放帧”映射到 capture time



同时轨迹用同样的 t_ns，Rerun 里按 t_ns 记录（timeline）

WebRTC DataChannel 本身就是为这种“媒体之外的数据”准备的 



两个版本的落地路线（建议你先 1 后 2）

版本 A：最快可用（1～2 天就能跑）





WebRTC：aiortc 点对点（同一局域网）



Rerun：后端 rerun.serve() 开一个 Web Viewer + WS



前端：你自己的网页里





左边 





右边 iframe 指向 Rerun viewer URL（或直接用 web-viewer 包）



同步：先做“粗同步”





轨迹按 wall time



video 只做“显示当前估计 capture time”（不做可拖拽回放）

优点：最省事，先把 pipeline 跑通

缺点：时间轴联动没那么完美

版本 B：产品形态（可拖拽回放 + 真同步）





WebRTC 上 SFU（多人看、弱网更稳）



每帧 capture timestamp 通过 DataChannel/SEI 传到前端



前端统一时间轴：





拖动到 t：Rerun 跳到 t（或让数据窗口化显示 t 附近）



Video 走“DVR/回放”逻辑（需要缓存：HLS/DASH/分片 WebRTC 录制二选一）



注意：WebRTC 天生是 live，要“可拖拽回放”必须引入缓存/录制/索引。



所以我建议：直播用 WebRTC，回放用录制文件（mp4/HLS），时间轴同一套。



你接下来怎么做（我给你一个清晰的任务拆分）

Step 0：先把 UI 骨架搭出来





一个网页：左 video、右 rerun viewer（iframe 或 JS 嵌入）

 

Step 1：Rerun 先通（最容易）





后端起一个 ingestion（WS/HTTP）



收到轨迹就 rerun.log(...)



用官方 web viewer serve 示例思路跑通端到端

 

Step 2：WebRTC 再通





aiortc 推 H264（硬编优先）



浏览器 

 播放

Step 3：加 DataChannel 时间戳





publisher 发 t_capture_ns



browser 显示“当前帧 capture time”



Rerun timeline 用同一 timebase



你如果愿意，我可以直接按你习惯给“工程模板”

我可以给你一个目录结构（frontend/backend）、接口定义（消息格式）、以及最小 Demo 的代码骨架（FastAPI + aiortc + rerun + React）。

你只要告诉我两点就行（不用长篇）：





你的视频源：OAK-D-W 在哪台机器上？（Linux/Jetson/PC/mac）



你希望多人同时看吗？（是=直接走 SFU；否=先 P2P）

