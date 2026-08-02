# Atlas Runtime v8.0 LTS

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/izualchou/atlas-runtime)](https://github.com/izualchou/atlas-runtime/releases)

**Atlas Runtime** 是一个运行在 Android 系统上，通过 Termux 实现的事件驱动型自动化运行时。

## ✨ 核心特性

* **Termux First**: 核心逻辑全部运行在 Termux 中，利用 termux-services (runit) 实现服务保活与自动重启。
* **事件驱动**: 通过 FIFO 命名管道接收触发信号，完全免疫 Android Doze 模式的网络限制。
* **进程安全**: Shell 子进程通过独立进程组隔离，超时清理安全可靠，绝不误杀父进程。
* **端到端背压控制**: SQLite 写入队列有界（1000），防止高并发下内存溢出。
* **原子快照**: 深拷贝冻结状态 + SHA256 校验，确保恢复一致性。
* **一键部署**: 提供自动化部署脚本，最大限度提高部署成功率。

## 🚀 快速部署

```bash
curl -fsSL https://raw.githubusercontent.com/izualchou/atlas-runtime/main/service/deploy.sh -o deploy.sh && bash deploy.sh
