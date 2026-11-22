# Get Skill Content

**GET /api/projects/{project_id}/skills/{skill_id}/content**

**Tags:** Skills

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|skill_id|string|Yes|The unique identifier of the skill.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|skill_md|string|The full SKILL.md content including frontmatter.|
|body|string|The markdown body of the skill.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
