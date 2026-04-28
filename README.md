# Sonolus SCP Repacker / Sonolus SCP 重打包工具

[English](#english) | [中文](#中文)

## English

Sonolus SCP Repacker is a tool for repackaging `.scp` Prosekai-style level packs from Sonolus to use a specified engine (currently supporting RUSH or NextRUSH+). Useful when you want updating old Prosekai levels that still use legacy engines.

This is a package metadata/resource rewriter. It does **not** convert Sonolus `LevelData`, so gameplay compatibility still depends on whether the original level data works with the selected engine.

### Web App

Use the hosted page:

<https://endoretic.github.io/SCP-Repacker/>

Select the levels `.scp`, choose the target engine, and download the rebuilt package.

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

Optional flags:

- `--no-replace-defaults`: keep the original level resource override settings.
- `--only-selected-engine`: include only the selected engine in the output package.
- `--keep-old-engines`: keep engines from the original levels package too.

### What It Changes

- Replaces each level's full `engine` object with the selected engine item.
- Updates level metadata in `sonolus/levels/list`, `sonolus/levels/info`, and individual `sonolus/levels/<level>` files.
- Merges `engines`, `skins`, `backgrounds`, `effects`, `particles`, and `repository` files from the resource package.
- Validates engine references and missing repository files before writing the output.

### Notes

- Delete older imports of the same collection in Sonolus before importing the rebuilt `.scp` to reduce cache/name collisions.
- If the rebuilt package imports but fails during gameplay, the likely issue is LevelData compatibility, not package repacking.

## 中文

Sonolus SCP Repacker 用于把 Sonolus 上的 `.scp` Prosekai 类关卡包重打包成使用指定 engine （当前为 `RUSH` 或 `NextRUSH+` ）的版本。当您想要更新使用旧版引擎的 Prosekai 关卡时非常有用。

这是一个“包元数据/资源重写工具”，不是谱面转换器。它不会转换 Sonolus `LevelData`，所以实际游玩是否正常仍取决于原始关卡数据是否兼容目标 engine。

### 网页版

直接使用网页：

<https://endoretic.github.io/SCP-Repacker/>

选择关卡 `.scp`、选择目标 engine，然后下载重打包后的文件。

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

可选参数：

- `--no-replace-defaults`：保留原关卡的资源覆盖设置。
- `--only-selected-engine`：输出包中只保留选中的 engine。
- `--keep-old-engines`：同时保留原关卡包里的旧 engines。

### 工具会做什么

- 用所选 engine 的完整 `item` 对象替换关卡里的 `engine`。
- 更新 `sonolus/levels/list`、`sonolus/levels/info` 和每个 `sonolus/levels/<level>`。
- 合并资源包里的 `engines`、`skins`、`backgrounds`、`effects`、`particles` 和 `repository`。
- 输出前检查 engine 引用和缺失的 repository 文件。

### 注意

- 导入新 `.scp` 前，建议先删除 Sonolus 里同名的旧导入包，减少缓存或命名冲突。
- 如果重打包后的文件能导入但游玩异常，通常是 LevelData 与目标 engine 不兼容，而不是打包流程本身的问题。
