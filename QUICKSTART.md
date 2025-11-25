# 快速开始指南

## 检查20个网站

### 步骤1：打开命令行

在Windows上：
1. 按 `Win + R`
2. 输入 `cmd` 并回车
3. 或者按 `Win + X`，选择"Windows PowerShell"或"命令提示符"

### 步骤2：进入TestConnect文件夹

```cmd
cd C:\Coding\COMP5355\TestConnect
```

（根据你的实际路径调整）

### 步骤3：安装依赖（如果还没安装）

```cmd
pip install -r requirements.txt
```

### 步骤4：运行检查

```cmd
py check_site_accessibility.py -n 20
```

或者如果 `python` 命令指向 Python 3：
```cmd
python check_site_accessibility.py -n 20
```

## 运行说明

- `-n 20` 表示检查20个未标记的网站
- 脚本会自动：
  - 跳过已标记的网站（第5列有值的）
  - 从第一个未标记的网站开始检查
  - 检查完成后更新CSV文件中的标记

## 标记说明

- **0**: 网站不可访问
- **1**: 网站可访问（但不确定是否有挖矿脚本）
- **2**: 网站可访问且资源超限（可能包含挖矿脚本）

## 输出文件

运行后会生成文件到以下文件夹：

- **`results/`** 文件夹：
  - `check_results_*.json` - 详细结果（JSON格式）
  - `report_*.txt` - 摘要报告
  - `valid_sites_*.txt` - 可访问网站列表（所有可访问的网站）
  - `mining_sites_*.txt` - **可能有挖矿脚本的网站列表**（推荐使用）

- **`logs/`** 文件夹：
  - `check_site_accessibility_*.log` - 运行日志

## 查看结果

```cmd
# 查看摘要报告
type results\report_*.txt

# 查看可能有挖矿脚本的网站列表（推荐）
type results\mining_sites_*.txt

# 查看所有可访问的网站列表
type results\valid_sites_*.txt

# 查看日志
type logs\check_site_accessibility_*.log

# 或者直接打开文件夹
explorer results
explorer logs
```

## 使用结果文件

生成的 `mining_sites_*.txt` 文件可以直接用于 `mining_detector.py`：

```cmd
# 在项目根目录
cd ..
python mining_detector.py -u TestConnect\results\mining_sites_20231201_120000.txt
```

## 继续检查更多网站

下次运行时，脚本会自动跳过已标记的网站，继续检查未标记的：

```cmd
python check_site_accessibility.py -n 50
```

## 注意事项

1. 每个连接最多持续30秒
2. 如果CPU或内存超过限制（默认80%），会立即断开并标记为2
3. 脚本会实时显示资源使用情况
4. CSV文件会自动更新，请确保有写入权限

---

## 检查挖矿网站连通性

如果你已经有了 `results/mining_sites.txt` 文件，可以使用 `check_miningsites_accessbility.py` 快速检查这些网站的连通性：

### 基本用法

```cmd
py check_miningsites_accessbility.py
```

### 功能说明

- 从 `results/mining_sites.txt` 读取URL列表（每行一个URL）
- 并发检查每个URL的连通性
- 将可访问的URL保存到 `results/accessible_miningsites.txt`

### 参数说明

```cmd
# 自定义输入文件
py check_miningsites_accessbility.py -i results/mining_sites.txt

# 自定义输出文件
py check_miningsites_accessbility.py -o results/accessible_miningsites.txt

# 自定义超时时间（15秒）
py check_miningsites_accessbility.py -t 15

# 自定义并发数（30个线程）
py check_miningsites_accessbility.py -w 30

# 组合使用
py check_miningsites_accessbility.py -t 15 -w 30
```

### 输出文件

- `results/accessible_miningsites.txt` - 可访问的网站列表（每行一个URL）
- `logs/check_miningsites_accessibility_*.log` - 运行日志

### 查看结果

```cmd
# 查看可访问的网站列表
type results\accessible_miningsites.txt

# 查看日志
type logs\check_miningsites_accessibility_*.log
```

