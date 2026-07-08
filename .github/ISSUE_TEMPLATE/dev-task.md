---
name: 开发任务
about: 基于已通过评审的 PRD 创建开发任务
title: "[Dev] "
labels: "ai-dev"
assignees: ""
---

## 关联 PRD

请填写已经合并到 `main` 的 PRD 文件路径：

- 

## 开发目标

说明本 Issue 要完成的开发内容。

## 影响范围

说明预计涉及的页面、接口、服务、数据表、配置或测试范围。

## 验收标准

- 

## AI 任务配置

```yaml
ai_task:
  prd_path: docs/requirements/xxx.md
  type: feature
  validation:
    - python -m unittest discover -s tests
  max_attempts: 2
  docker_required: false
```

## 备注

补充技术约束、接口约定、数据准备或测试环境说明。
