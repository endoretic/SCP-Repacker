# Sonolus SCP Repacker / Sonolus SCP 重打包工具

[English](#english) | [中文](#中文)

## English

Sonolus SCP Repacker repackages Sonolus `.scp` Prosekai-style level packs to use a selected target engine from the bundled resource pack.

Currently verified source engines:

- Next Sekai
- PJSekai+
- ProSeka R

Bundled target engines:

- RUSH (`rush`)
- NextRUSH+ (`NextRUSH_P`)

### How It Works

1. The tool reads the source `.scp` package and the bundled `engine.scp` resource pack.
2. It optionally converts supported PJSekai+ / ProSeka R style `LevelData` into the NextRUSH/RUSH target format when `--convert-level-data` is enabled.
3. It rewrites level metadata in both `sonolus/levels/list` and individual `sonolus/levels/<level>` files to use the selected target engine.
4. It updates default skin/background/effect/particle references to match the target engine resources unless `--no-replace-defaults` is used.
5. It merges target engine resources and repository files, validates references, and writes the rebuilt `.scp`.

### Web App

Use the hosted page:

<https://endoretic.github.io/SCP-Repacker/>

Select the levels `.scp`, choose the target engine, enable LevelData conversion for PJSekai+ / ProSeka R packages, and download the rebuilt package.

For local use:

```bash
python -m http.server
```

Then open <http://127.0.0.1:8000/>.

### CLI Usage

Requirements:

- Python 3.8+

List engines:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --list-engines
```

Repack with `RUSH`:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush
```

Repack with `NextRUSH+`:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine NextRUSH_P
```

Convert supported PJSekai+ / ProSeka R style LevelData while repacking:

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine NextRUSH_P --convert-level-data
```

Optional flags:

- `--convert-level-data`: convert supported PJSekai+ / ProSeka R style `LevelData` into the NextRUSH/RUSH target format before rewriting engine references.
- `--no-replace-defaults`: keep the original level resource override settings.
- `--only-selected-engine`: include only the selected engine in the output package.
- `--keep-old-engines`: keep engines from the original levels package too.

### Known Issues

- PJSekai+ `trace end flick` notes may be indistinguishable from normal slide end flick notes after `uscToLevelData()` has produced LevelData, because the source LevelData does not preserve the original trace end marker.
- PJSekai+ guide conversion may create a different `AnchorNote` graph than NextRUSH-generated LevelData. Guides should remain usable, but complex guide visuals may not be perfectly identical.

### Project Structure

```text
repack_sonolus_scp.py       CLI entry point
scp_repacker/
  archive.py                .scp zip IO, JSON helpers, repository validation
  metadata.py               Sonolus level/engine/resource metadata rewriting
  leveldata.py              PJSekai+ / ProSeka R LevelData conversion
assets/
  vendor/fflate.js          Browser zip/gzip dependency
  repack-leveldata.js       Browser LevelData conversion module
  repack-core.js            Browser repack API and validation flow
  app.js                    Web UI wiring
index.html                  Static GitHub Pages app
engine.scp                  Bundled target engine/resource pack
testdata/                   Local sample packages for verification
```

### Credits

- PJSekai+ / Chart Cyanvas engine and USC conversion reference: <https://github.com/sevenc-nanashi/sonolus-pjsekai-engine-extended>
- NextRUSH+ / Next Sekai LevelData format and conversion reference: <https://github.com/hyeon2006/sonolus-next-rush-plus-engine>
- Browser zip/gzip support uses fflate: <https://github.com/101arrowz/fflate>

All copyrights belong to their respective authors.

## 中文

Sonolus SCP Repacker 用于把 Sonolus `.scp` Prosekai 类关卡包重打包成使用资源包中指定目标 engine 的版本。

目前已验证的来源 engine：

- Next Sekai
- PJSekai+
- ProSeka R

内置目标 engine：

- RUSH (`rush`)
- NextRUSH+ (`NextRUSH_P`)

### 工作逻辑

1. 工具读取来源 `.scp` 关卡包和内置 `engine.scp` 资源包。
2. 启用 `--convert-level-data` 时，会先把已支持的 PJSekai+ / ProSeka R 风格 `LevelData` 转成 NextRUSH/RUSH 目标格式。
3. 工具会同时重写 `sonolus/levels/list` 和每个 `sonolus/levels/<level>` 中的关卡 metadata，让关卡引用所选目标 engine。
4. 默认会把 skin/background/effect/particle 的默认资源引用切到目标 engine 资源；使用 `--no-replace-defaults` 可保留原设置。
5. 工具会合并目标 engine 资源和 repository 文件，检查引用，然后写出新的 `.scp`。

### 网页版

直接使用网页：

<https://endoretic.github.io/SCP-Repacker/>

选择关卡 `.scp`、选择目标 engine；如果来源是 PJSekai+ / ProSeka R，启用 LevelData 转换，然后下载重打包后的文件。

本地运行：

```bash
python -m http.server
```

然后打开 <http://127.0.0.1:8000/>。

### 命令行用法

要求：

- Python 3.8+

列出可用 engines：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --list-engines
```

使用 `RUSH`：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine rush
```

使用 `NextRUSH+`：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine NextRUSH_P
```

重打包时转换已支持的 PJSekai+ / ProSeka R 风格 LevelData：

```bash
python repack_sonolus_scp.py levels.scp engine.scp output.scp --engine NextRUSH_P --convert-level-data
```

可选参数：

- `--convert-level-data`：在重写 engine 引用前，把已支持的 PJSekai+ / ProSeka R 风格 `LevelData` 转成 NextRUSH/RUSH 目标格式。
- `--no-replace-defaults`：保留原关卡的资源覆盖设置。
- `--only-selected-engine`：输出包中只保留选中的 engine。
- `--keep-old-engines`：同时保留原关卡包里的旧 engines。

### 已知问题

- PJSekai+ 的 `trace end flick` 在 `uscToLevelData()` 生成 LevelData 后可能无法和普通 slide end flick 区分，因为来源 LevelData 不保留原始 trace end 标记。
- PJSekai+ guide 转换出的 `AnchorNote` 图结构可能和 NextRUSH 直接生成的 LevelData 不完全一致。Guide 应该仍可用，但复杂 guide 的视觉表现可能无法完全一致。

### 目录结构

```text
repack_sonolus_scp.py       CLI 入口
scp_repacker/
  archive.py                .scp zip 读写、JSON helper、repository 校验
  metadata.py               Sonolus 关卡/engine/资源 metadata 重写
  leveldata.py              PJSekai+ / ProSeka R LevelData 转换
assets/
  vendor/fflate.js          网页端 zip/gzip 依赖
  repack-leveldata.js       网页端 LevelData 转换模块
  repack-core.js            网页端重打包 API 和校验流程
  app.js                    网页 UI 绑定
index.html                  GitHub Pages 静态页面
engine.scp                  内置目标 engine/资源包
testdata/                   本地验证用样本包
```

### Credit

- PJSekai+ / Chart Cyanvas engine 与 USC 转换参考：<https://github.com/sevenc-nanashi/sonolus-pjsekai-engine-extended>
- NextRUSH+ / Next Sekai LevelData 格式与转换逻辑参考：<https://github.com/hyeon2006/sonolus-next-rush-plus-engine>
- 网页端 zip/gzip 支持使用 fflate：<https://github.com/101arrowz/fflate>

所有版权归各自作者所有。
