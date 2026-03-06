# 通讯黑匣子 (BlackBox) 使用教程

**模块文件：** `user_function/src/blackbox.c` | `user_function/inc/blackbox.h`

---

## 1. 功能说明

黑匣子模块可以在测试过程中全程录制测试板与上位机、以及测试板与编码器之间的所有通讯帧，并支持**分段多次导出**，上位机可在测试过程中随时读取已记录的内容。

### 核心特性

- **滚动覆盖**：缓冲区满了后自动覆盖最旧的记录，保证最新数据不丢
- **分段导出**：`GetTestContent` 只清空缓冲区，**不关闭录制**，可多次调用
- **全局序号**：跨分段连续递增，方便拼接完整日志
- **零开销**：未开启时所有 Log 调用为空操作

### 四个通讯通道 + 事件日志

| 标签 | 方向 | 说明 |
|------|------|------|
| `[A]` | FCT上位机 → 测试板 | Modbus 接收帧 |
| `[a]` | 测试板 → FCT上位机 | Modbus 响应帧 |
| `[B]` | 测试板 → 编码器 | 编码器 DMA 发送帧 |
| `[b]` | 编码器 → 测试板 | 编码器 DMA 接收帧 |
| `[*]` | 内部事件 | 自定义文字日志 |

---

## 2. 使用步骤

### 第 1 步：开启黑匣子

测试开始前，FCT 脚本发送 Modbus 写入指令：

| 命令 | 帧格式 | 效果 |
|------|--------|------|
| 开启 | `05 06 00 20 5A A5 XX XX` | 清空缓冲区、序号归零、**开始录制** |
| 关闭 | `05 06 00 20 A5 5A XX XX` | **停止录制**（缓冲区保留，仍可读出） |

- 寄存器 `0x0020`，写入 `0x5AA5` 开启，写入 `0xA55A` 关闭
- CRC 由上位机自动计算填入

### 第 2 步：正常运行测试

测试期间无需任何额外操作，黑匣子在后台自动记录。

### 第 3 步：分段导出数据

测试过程中或测试结束后，发送 ASCII 字符串命令：

```
GetTestContent\r\n
```

测试板返回当前缓冲区中的全部记录，然后**清空缓冲区但保持录制**。

上位机可以**多次调用**，将每次返回的内容追加拼接成完整日志。

### 第 4 步：关闭黑匣子

测试结束后，发送关闭命令停止录制：

```
发送：05 06 00 20 A5 5A XX XX
```

关闭后缓冲区数据仍然保留，可以再发一次 `GetTestContent\r\n` 读取最后一批数据。

---

## 3. 数据格式

```
[00001][A][+00000ms] 05 06 00 04 00 01 58 3D
[00002][a][+00001ms] 05 06 00 04 00 01 58 3D
[00003][B][+00002ms] 25
[00004][b][+00003ms] 25 00 1A 3F 00 00 00 00 00 7C
[00005][*][+00004ms] Hall: sector=2 cnt=8 result=1
...
END
```

| 字段 | 说明 |
|------|------|
| `[00001]` | 全局序号（跨分段连续递增） |
| `[A]` | 方向标签 |
| `[+00002ms]` | 距黑匣子启动的时间偏移 |
| HEX 数据 | 通讯帧原始字节 |

### 特殊标记

| 标记 | 含义 |
|------|------|
| `END` | 本次导出结束 |
| `WRAPPED` | 本段发生过滚动覆盖（有旧数据被丢弃） |
| `EMPTY` | 缓冲区为空（无数据可导出） |

---

## 4. FCT 脚本集成示例

```python
# 1. 开启黑匣子
write_register(0x0020, 0x5AA5)

all_logs = []

# 2. 测试过程中分段读取
for i, step in enumerate(test_steps):
    execute(step)
    if (i + 1) % 30 == 0:  # 每 30 步读取一次
        data = send_ascii("GetTestContent\r\n")
        all_logs.append(data)

# 3. 关闭黑匣子
write_register(0x0020, 0xA55A)

# 4. 读取最后一批数据
data = send_ascii("GetTestContent\r\n")
all_logs.append(data)

# 保存完整日志
with open("blackbox_log.txt", "w", encoding="utf-8") as f:
    for segment in all_logs:
        f.write(segment)
```

---

## 5. 在代码中记录内部事件

在需要记录的 `.c` 文件顶部添加：
```c
#include "blackbox.h"
```

在关键节点调用：
```c
// Hall 校验结果
BlackBox_LogEvent("HallCW: %s pit=%d", g_MulMag.Hall.Result ? "PASS" : "FAIL", g_MotorEncoder.PitCnt);

// 单圈位置与转速
BlackBox_LogEvent("pos=%lu speed=%d", g_MulMag.SingleTurnPos, g_MotorEncoder.ActualSpeed);

// 测试状态切换
BlackBox_LogEvent("TestItem -> %d", g_MotorEncoder.TestItem);
```

> **注意：** 事件字符串最长 39 字符，超出截断。黑匣子未开启时为空操作，零开销。

---

## 6. 缓冲区信息

| 项目 | 数值 |
|------|------|
| 缓冲区条数 | 500 条 |
| 每条记录大小 | 46 Bytes |
| 总占用 SRAM | ≈ 22 KB |
| 满了后的行为 | **滚动覆盖最旧记录**（保证最新帧不丢） |
| 分段导出 | 支持（清空缓冲区但不停止录制） |
| 全局序号 | 跨段连续递增（0x0020 重新 Enable 才归零） |
