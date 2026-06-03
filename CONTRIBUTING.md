# 贡献指南

感谢你对穷观阵的关注！

## 如何贡献

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/xxx`
3. 提交更改：`git commit -m "feat: add xxx"`
4. 推送分支：`git push origin feature/xxx`
5. 发起 Pull Request

## 开发环境

```bash
pip install -r requirements.txt
python main.py
```

## 代码规范

- 使用中文注释和提交信息
- 日志使用 `logging` 模块，不要用 `print`
- 新增 fetcher 继承 `BaseFetcher` 或对应平台基类
- 新增游戏需要更新 `core/models.py` 中的配置

## 运行测试

```bash
python -m pytest tests/ -v
```

## 提交规范

- `feat:` 新功能
- `fix:` 修复 bug
- `refactor:` 重构
- `docs:` 文档更新
- `test:` 测试相关
- `chore:` 构建/工具

## 商业使用

本项目禁止未经授权的商业使用。如有商业合作需求，请联系版权持有人。
