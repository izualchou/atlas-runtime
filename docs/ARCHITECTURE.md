# Atlas Runtime v8.0 LTS 架构设计文档

> 完整架构设计请参见项目根目录 README.md。

## 设计原则

1. **Termux First**: 所有核心逻辑运行在 Termux 中
2. **事件驱动**: FIFO 管道触发，免疫 Doze 模式
3. **进程安全**: 独立进程组，超时安全清理
4. **背压控制**: 有界队列，防止 OOM
