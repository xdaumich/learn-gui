# Repro GUI (React + Playwright) — Project.md

目标：做一个极简 GUI，但**可录制/可回放**用户操作，让 agent（Playwright）能**稳定复现**问题；后续可扩展到机器人数据采集前端（dataset / traj / video / 标注）。

---

## 1. 核心痛点与原则

### 痛点
- 前端 debug 慢：问题难描述、难复现、依赖截图/手动操作路径。
- agent 很难“看见” GUI 的真实状态与时序。

### 原则（必须做到）
1. **所有交互 = Action**：UI 点击/拖动不直接写逻辑，只 `dispatch(action)`。
2. **可录制**：dispatch 时可记录成 `repro.json`。
3. **可回放**：读取 `repro.json`，按序 dispatch，得到同样状态。
4. **可测试**：Playwright 不依赖 UI 点按钮；优先通过 `window.dispatchAction(action)` 喂动作流。
5. **可观测**：暴露 `window.__APP_STATE__` 给测试断言；失败输出 trace/screenshot/video。

---

## 2. 技术栈与目录结构

### Tech stack
- Frontend: **React + Vite + TypeScript**
- E2E: **Playwright**
-（后续接 Python backend：FastAPI / WS / gRPC 等，先不做）

### Repo layout (MVP)

repro-gui/
src/
App.tsx
main.tsx
repro.ts           # action schema + repro helpers
tests/
repro.spec.ts      # playwright tests
playwright.config.ts
package.json
project.md

---

## 3. MVP 需求（第一阶段必须完成）

### GUI（最小）
- Counter（+1 / +5 / reset）
- Item list（输入 + Add item）
- Slider（0-100）

### Repro 能力（关键）
- Start Recording / Stop & Export repro.json
- Paste JSON & Replay
- URL 参数回放（可选）：`?repro=<base64(json)>`

### Test hooks（必须）
- `window.dispatchAction(action)`：外部/测试直接驱动
- `window.__APP_STATE__`：用于断言（count/items/slider）

### Playwright（必须）
- 1 条“纯 action 回放”测试（不点 UI）
- 1 条“点 UI 路径”测试（少量点击）
- 失败保留：trace + screenshot + video

---

## 4. Action Schema（MVP）

定义在 `src/repro.ts`：

- `reset`
- `inc {by?}`
- `add_item {text}`
- `set_slider {value}`
- `assert {name, equals}`

说明：
- `assert` 用于在回放中定位问题（类似健康检查）。
- 真实项目扩展时，沿用相同风格，例如：
  - `open_dataset`
  - `select_traj`
  - `open_video`
  - `seek`
  - `play`
  - `annotate_add`
  - `export_bundle`

---

## 5. 开发步骤（用 Cursor）

### Step A — 初始化
```bash
mkdir repro-gui && cd repro-gui
npm create vite@latest . -- --template react-ts
npm i
npm i -D @playwright/test
npx playwright install

Step B — 实现 Repro 基础
	•	新增 src/repro.ts（schema + downloadJson）
	•	App 中实现：
	•	reducer：applyAction(state, action)
	•	recorder：recording on/off，导出 repro.json
	•	replayer：读取 json，按序 dispatch
	•	测试钩子：window.dispatchAction + window.__APP_STATE__

Step C — Playwright
	•	新增 playwright.config.ts（webServer + trace/screenshot/video）
	•	新增 tests/repro.spec.ts
	•	agent-style replay via actions：只喂 action 流
	•	UI path works：走少量点击验证

⸻

6. 运行方式

Dev server

npm run dev

Run tests

npx playwright test

Debug tests（可选）

npx playwright test --ui


⸻

7. Agent 复现工作流（你要的核心）

你遇到 bug 时
	1.	GUI 点 Start Recording
	2.	做 5-10 秒操作复现
	3.	点 Stop & Export 下载 repro.json
	4.	把 repro.json 发给 agent

Agent 复现（两种）

A) 写/跑 Playwright：把 actions 喂给 window.dispatchAction（最稳）
B) 直接在 GUI 粘贴 repro.json 内容点击 Replay（便于肉眼确认）

失败产物（Playwright 自动）
	•	trace
	•	screenshot
	•	video（可选）

⸻

8. 质量与稳定性要求（防 flaky）
	•	关键控件必须带 data-testid
	•	测试不要 sleep（尽量用断言 + state hook）
	•	渲染/异步更新：通过 __APP_STATE__ 判断状态达成，而不是猜时间

⸻

9. 第二阶段：迁移到机器人数据采集 GUI（规划）

保持不变（最重要）
	•	dispatch(action) 模式
	•	录制/回放/导出 bundle
	•	Playwright 基于 action 的可复现测试

替换/新增
	•	Counter → dataset/traj 选择
	•	Slider → 时间轴（ms）
	•	Item list → 标注列表/事件列表
	•	视频：优先走标准 mp4/hls URL（不要自己推帧）
	•	traj：按需拉取（windowed fetch），避免一次性大数据

⸻

10. Done Definition（MVP 完成标准）
	•	npm run dev 能打开页面并操作
	•	能录制并导出 repro.json
	•	能粘贴 json 回放
	•	npx playwright test 全绿
	•	Playwright 失败时能看到 trace/screenshot/video（至少 trace + screenshot）

⸻

11. 后续增强（可选）
	•	Export Debug Bundle（zip：repro + logs + screenshots）
	•	scenario 目录：scenarios/<name>/repro.json
	•	CI：push 时自动跑 Playwright（防回归）
	•	更严格断言：video time advances、traj sync 等（为真实项目准备）

