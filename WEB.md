# 前端开发

监控面板用 Three.js + TypeScript + Vite 构建。

## 目录

```
web/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── main.ts              入口，组装页面
    ├── api.ts               所有后端接口封装
    ├── types.ts             类型定义
    ├── style.css            全局样式（玻璃拟态）
    ├── three/
    │   └── background.ts    三维背景（星云 + 线框球）
    └── ui/
        ├── dom.ts           DOM 工具（el / q / flash）
        ├── feeds.ts         帖子列表 + 统计
        ├── knowledge.ts     知识库管理
        └── config.ts        规则与 AI 设置
```

## 开发

```bash
cd web
pnpm install
pnpm run dev       # http://localhost:5173，自动代理 /api 到 8790
```

## 构建

```bash
pnpm run build     # 输出到 ../web_dist
```

构建产物由 `web_watcher.py` 直接服务：

- `web_dist/` 存在 → 用新界面
- 不存在 → 降级到 `web_watcher.py` 里内嵌的旧 HTML

## 三维背景

三层，全部在 `three/background.ts`：

| 层 | 技术 | 数量 |
|---|---|---|
| 远景星云 | Points + ShaderMaterial（球壳分布）| 2600 |
| 中景线框球 | Icosahedron + WireframeGeometry | 1 |
| 近景亮星 | Points + 自定义着色器（景深）| 220 |

鼠标移动时相机视差跟随（带缓动）。

WebGL 不可用时 `initBackground` 会抛异常，被 `main.ts` 的 try/catch 捕获，页面降级为纯色背景。

## 样式要点

| 效果 | 实现 |
|---|---|
| 玻璃卡片 | `backdrop-filter: blur(20px) saturate(140%)` |
| 渐变标题 | `background-clip: text` + `color: transparent` |
| 卡片悬停 | `transform: translateY(-3px)` + 边框变蓝 |
| 帖子命中 | `.feed.hit` 绿色底 + 绿色边框 |
| 加载动画 | `.spinner` 旋转边框 |

## 代码风格

- 零外部 UI 库，全部手写 DOM（`el()` 工具函数）
- 严格 TS（`strict: true`，`noUnusedLocals: true`）
- 组件用工厂函数返回 `{ node }`，不用 class

## 注意

`web_dist/` 不进 git（`.gitignore` 已含），部署包里有构建产物。
改前端后要重新 `pnpm run build` 才会反映到页面。
