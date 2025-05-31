# 错误处理器 i18n 支持

## 概述

`error_handlers.ts` 现在完全支持国际化（i18n），可以根据用户的语言设置显示相应的错误消息。

## 功能特性

### 自动翻译

- `KilnError` 类现在会自动使用翻译的错误消息
- `createKilnError` 函数会自动翻译未知错误和意外错误
- 错误名称（`this.name`）也会被翻译

### 新增的便利函数

#### `createTranslatedKilnError(errorKey, errorMessages?)`

创建一个使用特定翻译键的错误：

```typescript
const error = createTranslatedKilnError("no_model_selected")
// 英文: "No model selected"
// 中文: "未选择模型"
```

#### `createTranslatedKilnErrorWithParams(errorKey, params, errorMessages?)`

创建一个带参数的翻译错误（为将来扩展准备）：

```typescript
const error = createTranslatedKilnErrorWithParams("unexpected_error", {
  detail: "timeout",
})
```

## 可用的错误翻译键

以下是 `errors` 命名空间下可用的翻译键：

### 通用错误

- `unknown_error` - 发生未知错误
- `unexpected_error` - 意外错误
- `network_error` - 网络错误
- `server_error` - 服务器错误

### 项目和任务相关

- `loading_projects` - 加载项目时出错
- `loading_task` - 加载任务时出错
- `current_project_not_found` - 未找到当前项目
- `project_task_id_not_set` - 项目或任务ID未设置
- `could_not_load_task` - 无法加载任务

### 设置和配置

- `settings_not_found` - 未找到设置
- `no_response_from_server` - 服务器无响应
- `invalid_json_response` - 无效的JSON响应

### 模型和修复相关

- `no_model_selected` - 未选择模型
- `invalid_model_selected` - 选择的模型无效
- `repair_instructions_required` - 需要修复说明
- `no_repair_to_accept` - 没有可接受的修复
- `no_repair_to_edit` - 没有可编辑的修复

### 数据和操作相关

- `no_options_returned` - 未返回选项
- `missing_required_fields` - 缺少必填字段
- `failed_to_save_sample` - 保存样本失败
- `no_id_returned` - 未返回ID

### 微调和评估

- `could_not_load_finetune_dataset` - 无法加载微调数据集信息
- `could_not_load_available_models` - 无法加载可用于微调的模型
- `no_evaluation_method_selected` - 未选择评估方法

### 更新相关

- `failed_to_fetch_update_data` - 获取更新数据失败

## 使用示例

### 基本用法

```typescript
import {
  KilnError,
  createKilnError,
  createTranslatedKilnError,
} from "$lib/utils/error_handlers"

// 自动翻译的错误
try {
  // 一些可能失败的操作
} catch (e) {
  const error = createKilnError(e) // 自动翻译
  console.log(error.getMessage())
}

// 使用特定的翻译键
const modelError = createTranslatedKilnError("no_model_selected")
throw modelError
```

### 在现有代码中的迁移

将硬编码的错误消息：

```typescript
// 旧代码
throw new KilnError("No model selected", null)
```

替换为翻译版本：

```typescript
// 新代码
throw createTranslatedKilnError("no_model_selected")
```

## 添加新的错误翻译

1. 在 `src/lib/i18n/locales/en.json` 的 `errors` 部分添加英文翻译
2. 在 `src/lib/i18n/locales/zh-CN.json` 的 `errors` 部分添加中文翻译
3. 使用 `createTranslatedKilnError('your_new_key')` 来使用新的翻译

## 注意事项

- 所有现有的 `KilnError` 实例现在都会自动使用翻译的默认消息
- 如果提供了自定义消息，它将优先于翻译的默认消息
- 错误名称（`this.name`）现在也会被翻译为 "Kiln 错误" 或 "Kiln Error"
- 便利函数使用 `get(_)()` 来获取当前语言的翻译，确保在错误创建时使用正确的语言
