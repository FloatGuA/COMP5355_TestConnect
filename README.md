# 网站可访问性检查工具

## 功能

`check_site_accessibility.py` 用于检查CSV文件中的网站是否可访问。

**注意**: 这些网站已经确认包含挖矿脚本，本脚本只检查可访问性。

## 文件说明

- `check_site_accessibility.py` - 主检查脚本（从CSV文件检查网站可访问性，Windows兼容）
- `check_miningsites_accessbility.py` - 挖矿网站连通性检查脚本（从文本文件检查URL连通性）
- `Coinhive_site_list.csv` - 网站列表数据文件
- `requirements.txt` - Python依赖包列表
- `README.md` - 本说明文档

## 快速开始（Windows）

### 方法1：使用批处理脚本（推荐）

```cmd
# 检查前100个网站（测试用）
run_check.bat

# 检查所有网站
run_check_all.bat
```

### 方法2：直接运行Python脚本

```cmd
cd TestConnect
python check_site_accessibility.py
```

### 基本用法

```bash
cd TestConnect
python check_site_accessibility.py
```

### 参数说明

```bash
python check_site_accessibility.py [选项]

选项:
  -i, --input FILE     输入CSV文件路径 (默认: Coinhive_site_list.csv)
  -o, --output FILE    输出JSON文件路径 (默认: check_results_YYYYMMDD_HHMMSS.json)
  -r, --report FILE    摘要报告文件路径 (默认: report_YYYYMMDD_HHMMSS.txt)
  -l, --list FILE      可访问网站列表文件路径 (默认: valid_sites_YYYYMMDD_HHMMSS.txt)
  -n, --limit NUM      检查的域名数量（必需参数）
  -t, --timeout SEC    请求超时时间（秒）(默认: 10)
  -w, --workers NUM    最大并发线程数 (默认: 20)
  --max-duration SEC   每个连接的最大持续时间（秒，默认30）
  --cpu-limit PERCENT  CPU使用率限制（百分比，默认80%）
  --memory-limit MB    内存使用限制（MB，默认系统内存的80%）
  --threshold PERCENT  资源增长阈值（百分比），超过此值认为可能有挖矿脚本（默认50%）
```

### 示例

```bash
# 检查100个未标记的网站（必需参数）
python check_site_accessibility.py -n 100

# 检查50个未标记的网站，自定义超时
python check_site_accessibility.py -n 50 -t 15

# 指定输入文件和检查数量
python check_site_accessibility.py -i Coinhive_site_list.csv -n 200

# 自定义超时、并发数和最大持续时间
python check_site_accessibility.py -n 100 -t 15 -w 30 --max-duration 20

# 自定义资源增长阈值（例如：资源增长超过30%就认为有挖矿脚本）
python check_site_accessibility.py -n 100 --threshold 30
```

### 标记说明

脚本会在CSV文件的第5列添加标记：
- **0**: 网站不可访问
- **1**: 网站可访问，但资源增长未超过阈值（可能没有挖矿脚本）
- **2**: 网站可访问，且资源增长超过阈值（可能有挖矿脚本）

**检测原理**：
- 在访问网站前记录基线资源使用（CPU和内存）
- 访问网站后等待5秒，让挖矿脚本有时间运行
- 再次记录资源使用，计算增长百分比
- 如果资源增长超过阈值（默认50%），标记为2
- 如果资源增长未超过阈值，标记为1

脚本会自动：
- 跳过已标记的网站
- 从第一个未标记的网站开始检查
- 检查完成后更新CSV文件中的标记

## 输出文件

所有输出文件会自动保存到以下文件夹：

- **`results/`** - 存放结果文件
  - `check_results_*.json` - 详细结果（JSON格式）
  - `report_*.txt` - 摘要报告
  - `valid_sites_*.txt` - 可访问网站列表（所有可访问的网站）
  - `mining_sites_*.txt` - **可能有挖矿脚本的网站列表**（mark=2的网站，可直接用于mining_detector.py）

- **`logs/`** - 存放日志文件
  - `check_site_accessibility_*.log` - 详细的运行日志

这些文件夹会在首次运行时自动创建。

## 注意事项

1. **Windows兼容**: 脚本已适配Windows环境，支持中文路径和文件名
2. **SSL证书**: 脚本会忽略SSL证书错误，以便访问更多网站
3. **并发限制**: 默认20个并发线程，可根据网络情况调整
4. **超时设置**: 默认10秒超时，对于慢速网站可能需要增加
5. **大量网站**: CSV文件包含5000+网站，完整检查可能需要较长时间
6. **只检查可访问性**: 不检测挖矿脚本（已确认所有网站都包含挖矿脚本）
7. **资源限制**: 
   - 默认限制CPU使用率为系统80%
   - 默认限制内存使用为系统内存的80%
   - 每秒记录资源使用情况
   - 超过限制时会自动降低进程优先级并发出警告

## 安装依赖

### Windows

```cmd
pip install -r requirements.txt
```

或者直接安装：

```cmd
pip install requests urllib3 psutil tqdm
```

## 快速测试

```bash
# 只检查前10个网站
python check_site_accessibility.py --limit 10

# 查看结果
type report_*.txt
```

## 使用检查结果

检查完成后，可以使用生成的列表文件：

### 1. 可能有挖矿脚本的网站列表（推荐）

使用 `mining_sites_*.txt` 文件，这个文件只包含可访问且资源增长超过阈值的网站（mark=2）：

```bash
# 在项目根目录
python mining_detector.py -u TestConnect/results/mining_sites_20231201_120000.txt
```

### 2. 所有可访问的网站列表

使用 `valid_sites_*.txt` 文件，包含所有可访问的网站（mark=1和mark=2）：

```bash
# 在项目根目录
python mining_detector.py -u TestConnect/results/valid_sites_20231201_120000.txt
```

---

## 检查挖矿网站连通性

`check_miningsites_accessbility.py` 是一个简化的脚本，专门用于检查 `results/mining_sites.txt` 中的网站连通性。

### 功能

- 从文本文件读取URL列表（每行一个URL）
- 并发检查每个URL的连通性
- 将可访问的URL保存到输出文件

### 基本用法

```bash
# 使用默认参数（从 results/mining_sites.txt 读取，输出到 results/accessible_miningsites.txt）
python check_miningsites_accessbility.py
```

### 参数说明

```bash
python check_miningsites_accessbility.py [选项]

选项:
  -i, --input FILE     输入文件路径（每行一个URL）(默认: results/mining_sites.txt)
  -o, --output FILE    输出文件路径（可访问的URL列表）(默认: results/accessible_miningsites.txt)
  -t, --timeout SEC    请求超时时间（秒）(默认: 10)
  -w, --workers NUM    最大并发线程数 (默认: 20)
```

### 示例

```bash
# 使用默认参数
python check_miningsites_accessbility.py

# 自定义超时时间
python check_miningsites_accessbility.py -t 15

# 自定义并发数
python check_miningsites_accessbility.py -w 30

# 自定义输入和输出文件
python check_miningsites_accessbility.py -i results/mining_sites.txt -o results/accessible_miningsites.txt

# 组合使用
python check_miningsites_accessbility.py -t 15 -w 30
```

### 输出文件

- `results/accessible_miningsites.txt` - 可访问的网站列表（每行一个URL）
- `logs/check_miningsites_accessibility_*.log` - 运行日志

### 使用场景

这个脚本适用于：
- 你已经有了一个URL列表文件（如 `results/mining_sites.txt`）
- 只需要快速检查这些URL的连通性
- 不需要复杂的资源监控和挖矿检测功能

