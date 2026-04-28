# Sonolus SCP Repacker / Sonolus SCP 重打包工具

[SCP-Repacker](https://endoretic.github.io/SCP-Repacker/)
[English](#english) | [中文](#中文)

## English

### Overview

This repository contains `repack_sonolus_scp.py`, a Python script for rewriting a Sonolus `.scp` package so its levels use an engine from another `.scp` resource pack.

The script is designed for workflows such as:

- taking a level package that currently uses one engine
- selecting a target engine from a resource pack
- rewriting all level metadata to point to that engine
- merging selectable resources such as skins, backgrounds, effects, and particles
- rebuilding a new `.scp` package

This project is a package rewriter, not a chart converter.

### What The Script Does

- Reads Sonolus `.scp` files as zip archives.
- Lists available engines from a resource package.
- Replaces the full `engine` object in level metadata with the selected engine item.
- Rewrites all detected level metadata entry points:
  `sonolus/levels/list`, `sonolus/levels/info`, each `sonolus/levels/<level>`, and embedded level cards inside section data.
- Optionally resets level resource overrides so levels fall back to the selected engine defaults.
- Merges `skins`, `backgrounds`, `effects`, `particles`, `engines`, and `repository` entries from the resource pack.
- Rebuilds `engines/info` so it stays consistent with the final engine list.
- Runs validation checks for engine consistency and missing repository files.

### What The Script Does Not Do

- It does not convert Sonolus `LevelData`.
- It does not guarantee that level data made for one engine will run correctly on another engine.
- A rebuilt package may still fail in gameplay if the original chart data is incompatible with the selected engine runtime.

### Requirements

- Python 3.8+

### Static Web UI

This repository now also includes a browser version:

- `index.html`: static entry page
- `assets/styles.css`: page styles
- `assets/repack-core.js`: browser-side repack logic
- `assets/app.js`: UI wiring
- `assets/vendor/fflate.js`: bundled zip library

The web UI does **not** ask the user to manually provide `engine.scp`.
It automatically loads `./engine.scp`, so the user only needs to select the level package `.scp`.

Recommended local usage:

```bash
python -m http.server
```

Then open <http://127.0.0.1:8000/>.

### Repository Files

- `repack_sonolus_scp.py`: main script
- `sonolus_scp_repack_context.md`: project notes and structure findings
- `engine.scp`: example resource pack
- `index.html` + `assets/`: static browser UI

### Usage

List engines available in a resource package:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --list-engines
```

Repack using `rush` engine (Same as <https://sekairush.com/>):

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush
```

Repack using `NextRUSH_P` engine (Same as <https://untitledcharts.com/>):

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine NextRUSH_P
```

Include only the selected engine in the output package:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush --only-selected-engine
```

Keep original level resource overrides instead of resetting them to the selected engine defaults:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush --no-replace-defaults
```

Keep old engines from the original level package as well:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush --keep-old-engines
```

### Command Line Arguments

- `levels_scp`: input `.scp` package containing levels to rewrite
- `resource_scp`: input `.scp` package containing target engines and resources
- `output_scp`: output `.scp` package path
- `--list-engines`: print engines found in the resource package and exit
- `--engine <name>`: select the engine item name to use
- `--no-replace-defaults`: keep each level's original skin/background/effect/particle override state
- `--only-selected-engine`: write only the chosen engine into `sonolus/engines`
- `--keep-old-engines`: keep engines from the original level package in addition to imported resource-pack engines

### Typical Workflow

1. Prepare a level package `.scp`.
2. Prepare a resource package `.scp` that contains the target engine.
3. Run `--list-engines` to see the available engine names.
4. Repack with `--engine <name>`.
5. Import the rebuilt `.scp` into Sonolus.
6. If Sonolus already has an older import of the same collection, delete the old one first to reduce cache or name collisions.

### Output Summary

The script prints a summary including:

- detected source engines before patching
- number of rewritten level detail files
- number of rewritten `levels/list` and `levels/info` items
- merged resource list counts
- copied repository file counts
- validation results for engine mismatches
- validation results for default-resource override warnings
- validation results for missing repository files

### Notes

- The script rewrites the full `engine` object, not only visible fields such as `engine.name` or `engine.title`.
- By default, level override flags like `useBackground` are reset to `useDefault: true` when the selected engine provides a default resource, so old engine-specific overrides do not keep leaking into the rebuilt package.
- If you want to preserve those original overrides, use `--no-replace-defaults`.

---

## 中文

### 项目简介

本仓库提供了 `repack_sonolus_scp.py`，用于把一个 Sonolus `.scp` 包中的关卡重写为使用另一个 `.scp` 资源包中的引擎，并重新打包输出。

它适合这样的流程：

- 准备一个包含关卡的 `.scp`
- 准备一个包含目标引擎和资源的 `.scp`
- 从资源包中选择一个目标引擎
- 把关卡元数据里的引擎引用统一替换成该引擎
- 合并可选资源，例如皮肤、背景、特效、粒子
- 输出新的 `.scp`

这个项目是“包重写器”，不是“谱面转换器”。

### 脚本会做什么

- 把 Sonolus `.scp` 当作 zip 包读取。
- 列出资源包中可用的引擎。
- 用所选引擎的完整 `item` 对象替换关卡里的 `engine` 对象。
- 重写所有已识别到的关卡元数据入口：
  `sonolus/levels/list`、`sonolus/levels/info`、每个 `sonolus/levels/<level>`，以及 section 结构中嵌套的 level 卡片。
- 可选地把关卡资源覆盖项恢复为“跟随所选引擎默认资源”。
- 合并资源包中的 `skins`、`backgrounds`、`effects`、`particles`、`engines` 和 `repository`。
- 重新生成 `engines/info`，保证它和最终输出的引擎列表一致。
- 对引擎引用一致性和 repository 缺失文件做校验。

### 脚本不会做什么

- 不会转换 Sonolus `LevelData`。
- 不保证原本属于某个引擎的谱面数据一定能在另一个引擎上正常运行。
- 即使导入成功，如果原始谱面数据与目标引擎运行时不兼容，实机游玩仍可能报错、空谱或行为异常。

### 环境要求

- Python 3.8+

### 静态 Web 界面

本仓库现在还包含一个浏览器版本：

- `index.html`: 静态入口页面
- `assets/styles.css`: 页面样式
- `assets/repack-core.js`: 浏览器端重包（repack）逻辑
- `assets/app.js`: UI 交互逻辑关联
- `assets/vendor/fflate.js`: 内置的 zip 压缩库

Web UI **不需要**用户手动提供 `engine.scp`。
它会自动加载同目录下的 `./engine.scp`，因此用户只需选择关卡包 `.scp` 文件即可。

推荐的本地运行方式：

```bash
python -m http.server
```

然后访问 <http://127.0.0.1:8000/>。

### 仓库文件

- `repack_sonolus_scp.py`：主脚本
- `sonolus_scp_repack_context.md`：项目背景和结构分析记录
- `engine.scp`：示例资源包

### 使用方法

查看资源包内可用引擎：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --list-engines
```

使用 `rush` 进行重打包 (与<https://sekairush.com/>相同)：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush
```

使用 `NextRUSH_P` 进行重打包 (与<https://untitledcharts.com/>相同)：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine NextRUSH_P
```

输出包中只保留所选引擎：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush --only-selected-engine
```

保留关卡原本的资源覆盖设置，而不是改回所选引擎默认资源：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush --no-replace-defaults
```

同时保留原始关卡包中的旧引擎：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush --keep-old-engines
```

### 参数说明

- `levels_scp`：待重写的关卡 `.scp`
- `resource_scp`：包含目标引擎和资源的 `.scp`
- `output_scp`：输出文件路径
- `--list-engines`：列出资源包中的引擎后退出
- `--engine <name>`：指定要使用的引擎名
- `--no-replace-defaults`：保留每个关卡原有的皮肤、背景、特效、粒子覆盖状态
- `--only-selected-engine`：输出时仅写入选中的引擎到 `sonolus/engines`
- `--keep-old-engines`：除了导入资源包中的引擎外，也保留原关卡包中的旧引擎

### 典型流程

1. 准备一个包含关卡的 `.scp`。
2. 准备一个包含目标引擎的资源 `.scp`。
3. 用 `--list-engines` 查看资源包中的引擎名。
4. 使用 `--engine <name>` 执行重打包。
5. 将输出的 `.scp` 导入 Sonolus。
6. 如果 Sonolus 里已经导入过同名旧包，建议先删除旧包，再导入新包，以减少缓存或命名冲突。

### 输出信息

脚本会输出一组摘要信息，包括：

- 重写前检测到的原始关卡引擎
- 被重写的关卡详情文件数量
- 被重写的 `levels/list` 和 `levels/info` 条目数量
- 各类资源列表的合并数量
- 从两个输入包复制的 repository 文件数量
- 引擎引用不一致的校验结果
- 默认资源覆盖状态的校验结果
- repository 缺失引用的校验结果

### 说明

- 脚本替换的是完整 `engine` 对象，不只是 `engine.name` 或 `engine.title` 这种可见文本。
- 默认情况下，如果目标引擎带有默认皮肤、背景、特效、粒子，脚本会把关卡里的 `useSkin/useBackground/useEffect/useParticle` 统一拨回 `useDefault: true`，避免旧引擎的资源覆盖继续残留在新包中。
- 如果你希望保留这些原始覆盖项，请使用 `--no-replace-defaults`。
