#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查网站是否可访问
（网站已确认包含挖矿脚本，只需检查可访问性）
"""

import csv
import requests
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys
import psutil
import threading

# 尝试导入tqdm（进度条库）
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    # 简单的文本进度条实现（当tqdm未安装时使用）
    class tqdm:
        def __init__(self, total=None, desc=None, unit=None, bar_format=None):
            self.total = total
            self.desc = desc or ""
            self.unit = unit or "it"
            self.n = 0
            self.last_percent = -1
            self.postfix = {}
        
        def update(self, n=1):
            self.n += n
            if self.total:
                percent = int((self.n / self.total) * 100)
                # 每25%显示一次
                if percent >= 25 and self.last_percent < 25:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 25% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 25
                elif percent >= 50 and self.last_percent < 50:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 50% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 50
                elif percent >= 75 and self.last_percent < 75:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 75% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 75
                elif percent >= 100 and self.last_percent < 100:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 100% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 100
        
        def set_postfix(self, *args, **kwargs):
            """设置进度条后缀信息"""
            # 支持字典参数（通过解包）或关键字参数
            if args and isinstance(args[0], dict):
                self.postfix = args[0]
            else:
                self.postfix = kwargs
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            pass
        
        def close(self):
            pass

# 创建输出目录
os.makedirs('logs', exist_ok=True)
os.makedirs('results', exist_ok=True)

# 配置日志
log_file = os.path.join('logs', f'check_site_accessibility_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SiteAccessibilityChecker:
    """网站可访问性检查器"""
    
    def __init__(self, timeout: int = 10, max_workers: int = 20, 
                 cpu_limit_percent: Optional[float] = None, 
                 memory_limit_mb: Optional[int] = None,
                 resource_threshold_percent: float = 50.0):
        """
        初始化检查器
        
        Args:
            timeout: 请求超时时间（秒）
            max_workers: 最大并发线程数
            cpu_limit_percent: CPU使用率限制（百分比，None表示不限制）
            memory_limit_mb: 内存使用限制（MB，None表示不限制）
            resource_threshold_percent: 资源增长阈值（百分比），超过此值认为可能有挖矿脚本
        """
        self.timeout = timeout
        self.max_workers = max_workers
        
        # 资源限制配置
        self.cpu_limit_percent = cpu_limit_percent
        self.memory_limit_mb = memory_limit_mb
        self.resource_threshold_percent = resource_threshold_percent
        
        # 获取系统资源信息
        self.total_cpu_cores = psutil.cpu_count()
        self.total_memory_mb = psutil.virtual_memory().total // (1024 * 1024)
        
        # 如果没有指定限制，使用系统80%
        if self.cpu_limit_percent is None:
            self.cpu_limit_percent = 80.0
        if self.memory_limit_mb is None:
            self.memory_limit_mb = int(self.total_memory_mb * 0.8)
        
        # 当前进程
        self.process = psutil.Process()
        
        # 资源监控线程
        self.monitor_thread = None
        self.monitoring = False
        
        # 基线资源使用（用于比较）
        self.baseline_cpu = None
        self.baseline_memory = None
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        logger.info(f"系统资源: CPU核心数={self.total_cpu_cores}, 总内存={self.total_memory_mb}MB")
        logger.info(f"资源限制: CPU={self.cpu_limit_percent}%, 内存={self.memory_limit_mb}MB")
        logger.info(f"挖矿检测阈值: 资源增长超过{self.resource_threshold_percent}%认为可能有挖矿脚本")
        
        # 启动资源限制
        self._apply_resource_limits()
        self._start_resource_monitor()
        
        # 记录基线资源使用
        self._record_baseline()
        
    def normalize_url(self, domain: str) -> List[str]:
        """
        将域名转换为可能的URL列表
        
        Args:
            domain: 域名
            
        Returns:
            URL列表（先尝试https，再尝试http）
        """
        urls = []
        # 移除可能的协议前缀
        domain = domain.strip().replace('http://', '').replace('https://', '').replace('www.', '')
        
        if not domain:
            return urls
        
        # 尝试https和http
        urls.append(f'https://{domain}')
        urls.append(f'http://{domain}')
        urls.append(f'https://www.{domain}')
        urls.append(f'http://www.{domain}')
        
        return urls
    
    def _apply_resource_limits(self):
        """应用资源限制到当前进程"""
        try:
            # Windows上使用psutil设置进程优先级
            try:
                # 设置进程优先级为低于正常（降低CPU占用）
                self.process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                logger.info("已设置进程优先级为低于正常")
            except Exception as e:
                logger.warning(f"设置进程优先级失败: {e}")
            
            # 内存限制通过监控和警告实现
            # Windows上无法直接硬限制内存，但可以监控并在接近限制时警告
            logger.info("内存限制通过监控实现（Windows限制）")
            
        except Exception as e:
            logger.warning(f"应用资源限制失败: {e}")
    
    def _start_resource_monitor(self):
        """启动资源监控线程"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self.monitor_thread.start()
        logger.info("资源监控已启动")
    
    def _monitor_resources(self):
        """监控资源使用情况"""
        while self.monitoring:
            try:
                # 获取当前进程的资源使用
                cpu_percent = self.process.cpu_percent(interval=1)
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                
                # 计算系统CPU百分比
                cpu_system_percent = (cpu_percent / self.total_cpu_cores)
                memory_system_percent = (memory_mb / self.total_memory_mb) * 100
                
                # 每秒记录资源使用
                logger.info(f"资源使用 - CPU: {cpu_system_percent:.1f}% (系统), {cpu_percent:.1f}% (单核), "
                           f"内存: {memory_system_percent:.1f}% (系统), {memory_mb:.1f}MB")
                
                # 检查是否超过限制
                if cpu_system_percent > self.cpu_limit_percent:
                    logger.warning(f"⚠️ CPU使用率超过限制: {cpu_system_percent:.1f}% > {self.cpu_limit_percent}%")
                    # 尝试进一步降低优先级
                    try:
                        self.process.nice(psutil.IDLE_PRIORITY_CLASS)
                    except Exception:
                        pass
                
                if memory_mb > self.memory_limit_mb:
                    logger.warning(f"⚠️ 内存使用超过限制: {memory_mb:.1f}MB > {self.memory_limit_mb}MB")
                    # 如果内存使用过高，可以尝试清理
                    if memory_mb > self.memory_limit_mb * 1.2:
                        logger.error(f"⚠️⚠️ 内存使用严重超标，建议减少并发数或停止检查")
                
                time.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                logger.debug(f"资源监控出错: {e}")
                time.sleep(1)
    
    def stop_monitoring(self):
        """停止资源监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _record_baseline(self):
        """记录基线资源使用（在检查网站前）"""
        try:
            # 等待一小段时间让系统稳定
            time.sleep(0.5)
            cpu_percent = self.process.cpu_percent(interval=0.5)
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            
            self.baseline_cpu = cpu_percent
            self.baseline_memory = memory_mb
            
            logger.debug(f"基线资源: CPU={cpu_percent:.1f}%, 内存={memory_mb:.1f}MB")
        except Exception as e:
            logger.debug(f"记录基线资源失败: {e}")
            self.baseline_cpu = 0.0
            self.baseline_memory = 0.0
    
    def _get_current_resource_usage(self) -> tuple:
        """获取当前资源使用情况"""
        try:
            cpu_percent = self.process.cpu_percent(interval=0.1)
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            return cpu_percent, memory_mb
        except Exception:
            return 0.0, 0.0
    
    def _check_resource_exceeded(self) -> bool:
        """检查资源是否超过限制"""
        try:
            cpu_percent, memory_mb = self._get_current_resource_usage()
            cpu_system_percent = (cpu_percent / self.total_cpu_cores)
            
            # 如果CPU或内存超过限制，返回True
            if cpu_system_percent > self.cpu_limit_percent:
                logger.warning(f"⚠️ CPU超过限制: {cpu_system_percent:.1f}% > {self.cpu_limit_percent}%")
                return True
            
            if memory_mb > self.memory_limit_mb:
                logger.warning(f"⚠️ 内存超过限制: {memory_mb:.1f}MB > {self.memory_limit_mb}MB")
                return True
            
            return False
        except Exception:
            return False
    
    def _check_mining_by_resource_increase(self, baseline_cpu: float, baseline_memory: float) -> bool:
        """
        通过资源增长判断是否有挖矿脚本
        
        Args:
            baseline_cpu: 基线CPU使用率
            baseline_memory: 基线内存使用（MB）
            
        Returns:
            True表示可能有挖矿脚本
        """
        try:
            current_cpu, current_memory = self._get_current_resource_usage()
            
            # 计算增长百分比
            if baseline_cpu > 0:
                cpu_increase = ((current_cpu - baseline_cpu) / baseline_cpu) * 100
            else:
                cpu_increase = 100 if current_cpu > 0 else 0
            
            if baseline_memory > 0:
                memory_increase = ((current_memory - baseline_memory) / baseline_memory) * 100
            else:
                memory_increase = 100 if current_memory > 0 else 0
            
            # 如果CPU或内存增长超过阈值，认为可能有挖矿脚本
            has_mining = (cpu_increase > self.resource_threshold_percent or 
                         memory_increase > self.resource_threshold_percent)
            
            if has_mining:
                logger.info(f"资源增长检测: CPU增长={cpu_increase:.1f}%, 内存增长={memory_increase:.1f}% "
                          f"(阈值={self.resource_threshold_percent}%)")
            
            return has_mining
        except Exception:
            return False
    
    def check_url_accessible(self, url: str, max_duration: int = 30) -> Dict:
        """
        检查URL是否可访问
        
        Args:
            url: 要检查的URL
            
        Returns:
            包含访问结果的字典
        """
        result = {
            'url': url,
            'accessible': False,
            'status_code': None,
            'error': None,
            'redirect_url': None,
            'response_time': None
        }
        
        try:
            start_time = time.time()
            # 使用较短的超时时间，但不超过max_duration
            request_timeout = min(self.timeout, max_duration)
            
            # 检查资源使用，如果超过限制则立即返回
            if self._check_resource_exceeded():
                result['error'] = 'Resource limit exceeded'
                result['accessible'] = False
                return result
            
            response = self.session.get(
                url,
                timeout=request_timeout,
                allow_redirects=True,
                verify=False  # 忽略SSL证书错误
            )
            response_time = time.time() - start_time
            
            # 检查是否超过最大持续时间
            if response_time > max_duration:
                result['error'] = f'Exceeded max duration ({max_duration}s)'
                result['accessible'] = False
                return result
            
            # 再次检查资源使用
            if self._check_resource_exceeded():
                result['error'] = 'Resource limit exceeded after request'
                result['accessible'] = False
                return result
            
            result['accessible'] = True
            result['status_code'] = response.status_code
            result['response_time'] = round(response_time, 2)
            result['redirect_url'] = response.url if response.url != url else None
            
            # 检查是否是重定向到其他域名
            if result['redirect_url']:
                original_domain = urlparse(url).netloc
                redirect_domain = urlparse(result['redirect_url']).netloc
                if original_domain != redirect_domain:
                    result['redirected'] = True
                    result['redirect_domain'] = redirect_domain
                else:
                    result['redirected'] = False
            else:
                result['redirected'] = False
                
        except requests.exceptions.Timeout:
            result['error'] = 'Timeout'
        except requests.exceptions.ConnectionError:
            result['error'] = 'ConnectionError'
        except requests.exceptions.SSLError:
            result['error'] = 'SSLError'
        except requests.exceptions.RequestException as e:
            result['error'] = str(e)
        except Exception as e:
            result['error'] = f'Unexpected error: {str(e)}'
            
        return result
    
    def check_single_site(self, domain: str, max_duration: int = 30) -> Dict:
        """
        检查单个网站
        
        Args:
            domain: 域名
            
        Returns:
            检查结果字典
        """
        result = {
            'domain': domain,
            'accessible': False,
            'final_url': None,
            'status_code': None,
            'response_time': None,
            'error': None,
            'checked_at': datetime.now().isoformat(),
            'baseline_cpu': None,
            'baseline_memory': None,
            'current_cpu': None,
            'current_memory': None,
            'cpu_increase': None,
            'memory_increase': None
        }
        
        urls = self.normalize_url(domain)
        
        if not urls:
            result['error'] = 'Invalid domain'
            result['mark'] = 0  # 无效域名，标记为0
            return result
        
        # 尝试每个URL
        for url in urls:
            # 检查资源是否超过限制
            if self._check_resource_exceeded():
                result['error'] = 'Resource limit exceeded before connection'
                result['accessible'] = False
                # 资源超限，标记为2（可访问且有挖矿脚本，因为超限说明可能有恶意行为）
                result['mark'] = 2
                logger.warning(f"⚠️ {domain} - 资源超限，标记为2")
                return result
            
            access_result = self.check_url_accessible(url, max_duration)
            
            if access_result['accessible']:
                result['accessible'] = True
                result['final_url'] = access_result['redirect_url'] or url
                result['status_code'] = access_result['status_code']
                result['response_time'] = access_result['response_time']
                
                # 记录访问前的资源使用（基线）
                baseline_cpu, baseline_memory = self._get_current_resource_usage()
                result['baseline_cpu'] = baseline_cpu
                result['baseline_memory'] = baseline_memory
                
                # 等待5秒让挖矿脚本运行
                logger.debug(f"{domain} - 等待5秒以检测资源使用变化...")
                time.sleep(5)
                
                # 记录访问后的资源使用
                current_cpu, current_memory = self._get_current_resource_usage()
                result['current_cpu'] = current_cpu
                result['current_memory'] = current_memory
                
                # 计算资源增长
                if baseline_cpu > 0:
                    cpu_increase = ((current_cpu - baseline_cpu) / baseline_cpu) * 100
                else:
                    cpu_increase = 100 if current_cpu > 0 else 0
                
                if baseline_memory > 0:
                    memory_increase = ((current_memory - baseline_memory) / baseline_memory) * 100
                else:
                    memory_increase = 100 if current_memory > 0 else 0
                
                result['cpu_increase'] = cpu_increase
                result['memory_increase'] = memory_increase
                
                # 检查资源是否超过限制
                if self._check_resource_exceeded():
                    result['error'] = 'Resource limit exceeded during connection'
                    result['mark'] = 2  # 资源超限，标记为2（可能有挖矿脚本）
                    logger.warning(f"⚠️ {domain} - 连接后资源超限，标记为2")
                    return result
                
                # 通过资源增长判断是否有挖矿脚本
                has_mining = self._check_mining_by_resource_increase(baseline_cpu, baseline_memory)
                
                if has_mining:
                    result['mark'] = 2  # 资源增长超过阈值，可能有挖矿脚本
                    logger.info(f"✓ {domain} -> {result['final_url']} (状态码: {result['status_code']}, "
                              f"响应时间: {result['response_time']}s, 停留5秒后 "
                              f"CPU增长: {cpu_increase:.1f}%, 内存增长: {memory_increase:.1f}%, 标记: 2)")
                else:
                    result['mark'] = 1  # 可访问但资源增长未超过阈值，可能没有挖矿脚本
                    logger.info(f"✓ {domain} -> {result['final_url']} (状态码: {result['status_code']}, "
                              f"响应时间: {result['response_time']}s, 停留5秒后 "
                              f"CPU增长: {cpu_increase:.1f}%, 内存增长: {memory_increase:.1f}%, 标记: 1)")
                break  # 找到可访问的URL就停止
            else:
                result['error'] = access_result['error']
                # 如果是因为资源超限，标记为2
                if 'Resource limit exceeded' in access_result.get('error', ''):
                    result['mark'] = 2
                    logger.warning(f"⚠️ {domain} - 资源超限，标记为2")
                    return result
        
        if not result['accessible']:
            result['mark'] = 0  # 不可访问，标记为0
            logger.debug(f"✗ {domain} - 不可访问: {result['error']}, 标记: 0")
        
        return result
    
    def check_sites_from_csv(self, csv_file: str, output_file: Optional[str] = None, 
                            limit: Optional[int] = None, max_duration: int = 30) -> List[Dict]:
        """
        从CSV文件读取域名并检查
        
        Args:
            csv_file: CSV文件路径
            output_file: 输出JSON文件路径（可选）
            limit: 限制检查的域名数量（可选）
            
        Returns:
            检查结果列表
        """
        results = []
        domains_with_index = []  # 存储(行索引, 域名, 当前标记)
        all_rows = []  # 存储所有行，用于后续更新
        
        # 读取CSV文件，查找未标记的网站
        logger.info(f"读取CSV文件: {csv_file}")
        try:
            # 先读取所有行
            with open(csv_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
                reader = csv.reader(f)
                all_rows = list(reader)
            
            # 检查是否有标记列（第5列，索引4）
            has_mark_column = False
            if len(all_rows) > 0 and len(all_rows[0]) > 4:
                has_mark_column = True
            
            # 从第3行开始（跳过标题和Last update行）
            start_row = 2
            unmarked_count = 0
            
            for row_idx in range(start_row, len(all_rows)):
                row = all_rows[row_idx]
                
                # 只读取第三列（域名）
                if len(row) >= 3 and row[2]:  # 第三列是域名
                    domain = row[2].strip()
                    if domain:
                        # 检查标记列（第5列，索引4）
                        current_mark = None
                        if has_mark_column and len(row) > 4:
                            try:
                                current_mark = int(row[4].strip()) if row[4].strip() else None
                            except (ValueError, IndexError):
                                current_mark = None
                        
                        # 只处理未标记的网站
                        if current_mark is None or current_mark == '':
                            domains_with_index.append((row_idx, domain, current_mark))
                            unmarked_count += 1
                            
                            # 如果指定了限制，达到限制就停止
                            if limit and len(domains_with_index) >= limit:
                                break
            
            logger.info(f"找到 {unmarked_count} 个未标记的域名，将检查 {len(domains_with_index)} 个")
            
            if len(domains_with_index) == 0:
                logger.info("所有网站都已标记，无需检查")
                return results
            
            # 提取域名列表
            domains = [item[1] for item in domains_with_index]
        except FileNotFoundError:
            logger.error(f"文件不存在: {csv_file}")
            return results
        except Exception as e:
            logger.error(f"读取CSV文件失败: {e}")
            return results
        
        # 并发检查
        logger.info(f"开始检查，并发数: {self.max_workers}, 超时: {self.timeout}秒, 最大持续时间: {max_duration}秒")
        accessible_count = 0
        
        # 创建进度条
        progress_desc = "检查网站"
        with tqdm(total=len(domains), desc=progress_desc, unit="个", 
                  bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_domain = {
                    executor.submit(self.check_single_site, domain, max_duration): domain 
                    for domain in domains
                }
                
                completed = 0
                results_dict = {}  # 用于存储结果，key为域名
                last_logged_percent = -1  # 记录上次日志输出的百分比
                
                for future in as_completed(future_to_domain):
                    completed += 1
                    domain = future_to_domain[future]
                    
                    try:
                        result = future.result()
                        result['row_index'] = None  # 稍后设置
                        # 确保有mark字段
                        if 'mark' not in result:
                            result['mark'] = 0 if not result.get('accessible') else 1
                        results_dict[domain] = result
                        
                        if result['accessible']:
                            accessible_count += 1
                        
                        # 更新进度条
                        pbar.update(1)
                        # 防止除零错误
                        success_rate = (accessible_count/completed*100) if completed > 0 else 0.0
                        pbar.set_postfix({
                            '可访问': accessible_count,
                            '成功率': f'{success_rate:.1f}%'
                        })
                        
                        # 每25%显示一次详细进度（25%, 50%, 75%, 100%）
                        current_percent = int((completed / len(domains)) * 100)
                        percent_milestones = [25, 50, 75, 100]
                        for milestone in percent_milestones:
                            if current_percent >= milestone and last_logged_percent < milestone:
                                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                                # 防止除零错误
                                success_rate = (accessible_count/completed*100) if completed > 0 else 0.0
                                logger.info(f"进度: {milestone}% ({completed}/{len(domains)}) - "
                                          f"可访问: {accessible_count}, "
                                          f"成功率: {success_rate:.1f}%")
                                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                                last_logged_percent = milestone
                                break
                            
                    except Exception as e:
                        logger.error(f"检查 {domain} 时出错: {e}")
                        results_dict[domain] = {
                            'domain': domain,
                            'accessible': False,
                            'error': str(e),
                            'mark': 0,
                            'checked_at': datetime.now().isoformat(),
                            'row_index': None
                        }
                        pbar.update(1)
            
            # 将结果按原始顺序排列，并设置行索引
            for row_idx, domain, _ in domains_with_index:
                if domain in results_dict:
                    results_dict[domain]['row_index'] = row_idx
                    results.append(results_dict[domain])
        
        # 更新CSV文件中的标记
        self._update_csv_marks(csv_file, results, all_rows)
        
        # 保存结果
        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"结果已保存到: {output_file}")
            except Exception as e:
                logger.error(f"保存结果文件失败: {e}")
        
        # 停止资源监控
        self.stop_monitoring()
        
        # 统计信息
        mark_0_count = sum(1 for r in results if r.get('mark') == 0)
        mark_1_count = sum(1 for r in results if r.get('mark') == 1)
        mark_2_count = sum(1 for r in results if r.get('mark') == 2)
        
        logger.info("="*60)
        logger.info("检查完成！")
        logger.info(f"总域名数: {len(domains)}")
        logger.info(f"可访问: {accessible_count}")
        logger.info(f"不可访问: {len(domains) - accessible_count}")
        # 防止除零错误
        success_rate = (accessible_count/len(domains)*100) if len(domains) > 0 else 0.0
        logger.info(f"成功率: {success_rate:.1f}%")
        logger.info(f"标记统计: 0(不可访问)={mark_0_count}, 1(可访问)={mark_1_count}, 2(资源超限)={mark_2_count}")
        logger.info("="*60)
        
        return results
    
    def _update_csv_marks(self, csv_file: str, results: List[Dict], all_rows: List[List[str]]):
        """更新CSV文件中的标记列"""
        try:
            # 确保所有行都有5列（添加mark列）
            for row in all_rows:
                while len(row) < 5:
                    row.append('')
            
            # 如果第一行是标题行，确保第5列有标题
            if len(all_rows) > 0:
                if len(all_rows[0]) >= 4 and all_rows[0][0] == 'Pixalate':
                    # 这是标题行，添加mark列标题
                    if len(all_rows[0]) < 5 or not all_rows[0][4]:
                        all_rows[0][4] = 'Mark'
            
            # 更新标记
            updated_count = 0
            for result in results:
                row_idx = result.get('row_index')
                if row_idx is not None and row_idx < len(all_rows):
                    row = all_rows[row_idx]
                    mark = result.get('mark', 0)
                    
                    # 确保有足够的列
                    while len(row) < 5:
                        row.append('')
                    
                    # 更新第5列（索引4）的标记
                    old_mark = row[4] if len(row) > 4 else ''
                    row[4] = str(mark)
                    if old_mark != str(mark):
                        updated_count += 1
            
            # 写回CSV文件
            # 创建备份
            backup_file = csv_file + '.backup'
            try:
                import shutil
                if os.path.exists(csv_file):
                    shutil.copy2(csv_file, backup_file)
                    logger.debug(f"已创建备份文件: {backup_file}")
            except Exception:
                pass  # 备份失败不影响主流程
            
            # 尝试多次写入（处理文件被占用的情况）
            max_retries = 3
            retry_delay = 1
            for attempt in range(max_retries):
                try:
                    # 检查文件是否只读
                    if os.path.exists(csv_file):
                        import stat
                        file_stat = os.stat(csv_file)
                        # Windows上检查文件属性
                        if file_stat.st_mode & stat.S_IWRITE == 0:
                            logger.error(f"CSV文件是只读的: {csv_file}")
                            logger.error(f"请右键点击文件 -> 属性 -> 取消'只读'选项")
                            break
                    
                    # 尝试写入
                    with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerows(all_rows)
                    
                    logger.info(f"已更新CSV文件中的标记: {csv_file} (更新了 {updated_count} 行)")
                    break  # 成功写入，退出重试循环
                    
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"写入CSV文件失败（尝试 {attempt + 1}/{max_retries}），{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        logger.error(f"更新CSV文件失败: 权限被拒绝（已重试{max_retries}次）")
                        logger.error(f"文件路径: {os.path.abspath(csv_file)}")
                        logger.error(f"可能的原因:")
                        logger.error(f"  1. 文件被其他程序打开（Excel、记事本、VS Code、Cursor等）")
                        logger.error(f"  2. 文件是只读的（右键 -> 属性 -> 取消'只读'）")
                        logger.error(f"  3. 没有写入权限（尝试以管理员身份运行）")
                        logger.error(f"  4. 文件被防病毒软件锁定")
                        logger.error(f"建议: 关闭所有可能打开该文件的程序，然后重新运行脚本")
                except Exception as e:
                    logger.error(f"更新CSV文件失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    break
                    
        except Exception as e:
            logger.error(f"更新CSV标记时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def generate_summary_report(self, results: List[Dict], report_file: str):
        """
        生成摘要报告
        
        Args:
            results: 检查结果列表
            report_file: 报告文件路径
        """
        accessible_sites = [r for r in results if r['accessible']]
        inaccessible_sites = [r for r in results if not r['accessible']]
        
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("="*60 + "\n")
                f.write("网站可访问性检查报告\n")
                f.write("="*60 + "\n\n")
                f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总域名数: {len(results)}\n")
                f.write(f"可访问: {len(accessible_sites)}\n")
                f.write(f"不可访问: {len(inaccessible_sites)}\n")
                f.write(f"成功率: {len(accessible_sites)/len(results)*100:.1f}%\n\n")
                
                f.write("="*60 + "\n")
                f.write("可访问的网站:\n")
                f.write("="*60 + "\n\n")
                
                for site in accessible_sites:
                    f.write(f"域名: {site['domain']}\n")
                    f.write(f"URL: {site['final_url']}\n")
                    f.write(f"状态码: {site['status_code']}\n")
                    if site.get('response_time'):
                        f.write(f"响应时间: {site['response_time']}秒\n")
                    f.write("\n")
                
                f.write("\n" + "="*60 + "\n")
                f.write("不可访问的网站（前20个）:\n")
                f.write("="*60 + "\n\n")
                
                for site in inaccessible_sites[:20]:
                    f.write(f"域名: {site['domain']}\n")
                    f.write(f"错误: {site.get('error', 'Unknown')}\n")
                    f.write("\n")
                
                if len(inaccessible_sites) > 20:
                    f.write(f"... 还有 {len(inaccessible_sites) - 20} 个不可访问的网站\n")
            
            logger.info(f"摘要报告已保存到: {report_file}")
        except Exception as e:
            logger.error(f"生成报告失败: {e}")
    
    def generate_valid_sites_list(self, results: List[Dict], output_file: str):
        """
        生成可访问网站列表（用于mining_detector.py）
        
        Args:
            results: 检查结果列表
            output_file: 输出文件路径
        """
        valid_sites = [r['final_url'] for r in results if r['accessible'] and r['final_url']]
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for site in valid_sites:
                    f.write(f"{site}\n")
            
            logger.info(f"可访问网站列表已保存到: {output_file}")
            logger.info(f"共 {len(valid_sites)} 个可访问的网站")
        except Exception as e:
            logger.error(f"保存网站列表失败: {e}")
    
    def generate_mining_sites_list(self, csv_file: str, output_file: str):
        """
        从CSV文件中读取所有标记为2的网站，并保存到同一个文件
        
        Args:
            csv_file: CSV文件路径
            output_file: 输出文件路径（所有标记为2的网站都保存到这里）
        """
        mining_sites = set()  # 使用set避免重复
        
        try:
            # 从CSV文件中读取所有标记为2的网站
            with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                # 从第3行开始（跳过标题和Last update行）
                start_row = 2
                for row_idx in range(start_row, len(rows)):
                    row = rows[row_idx]
                    
                    # 检查是否有标记列（第5列，索引4）
                    if len(row) >= 5:
                        try:
                            mark = int(row[4].strip()) if row[4].strip() else None
                            if mark == 2:
                                # 标记为2，尝试获取URL
                                domain = row[2].strip() if len(row) > 2 else ""
                                if domain:
                                    # 构造URL（尝试https，如果失败则用http）
                                    url = f"https://{domain}"
                                    mining_sites.add(url)
                        except (ValueError, IndexError):
                            continue
            
            # 读取现有文件中的网站（如果文件存在）
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            site = line.strip()
                            if site:
                                mining_sites.add(site)
                except Exception as e:
                    logger.warning(f"读取现有挖矿网站列表失败: {e}，将创建新文件")
            
            # 写入所有标记为2的网站（去重后）
            mining_sites_list = sorted(list(mining_sites))
            with open(output_file, 'w', encoding='utf-8') as f:
                for site in mining_sites_list:
                    f.write(f"{site}\n")
            
            logger.info(f"所有标记为2的网站列表已保存到: {output_file}")
            logger.info(f"共 {len(mining_sites_list)} 个可能有挖矿脚本的网站（已去重）")
        except FileNotFoundError:
            logger.error(f"CSV文件不存在: {csv_file}")
        except Exception as e:
            logger.error(f"生成挖矿网站列表失败: {e}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='检查网站是否可访问（网站已确认包含挖矿脚本）')
    parser.add_argument('-i', '--input', default='Coinhive_site_list.csv',
                       help='输入CSV文件路径 (默认: Coinhive_site_list.csv)')
    parser.add_argument('-o', '--output', default=None,
                       help='输出JSON文件路径 (默认: check_results_YYYYMMDD_HHMMSS.json)')
    parser.add_argument('-r', '--report', default=None,
                       help='摘要报告文件路径 (默认: report_YYYYMMDD_HHMMSS.txt)')
    parser.add_argument('-l', '--list', default=None,
                       help='可访问网站列表文件路径 (默认: valid_sites_YYYYMMDD_HHMMSS.txt)')
    parser.add_argument('-m', '--mining-list', default=None,
                       help='可能有挖矿脚本的网站列表文件路径 (默认: results/mining_sites.txt，所有标记为2的网站都保存到这里)')
    parser.add_argument('-t', '--timeout', type=int, default=10,
                       help='请求超时时间（秒）(默认: 10)')
    parser.add_argument('-w', '--workers', type=int, default=20,
                       help='最大并发线程数 (默认: 20)')
    parser.add_argument('-n', '--limit', type=int, required=True,
                       help='检查的域名数量（必需参数）')
    parser.add_argument('--cpu-limit', type=float, default=None,
                       help='CPU使用率限制（百分比，默认80%%）')
    parser.add_argument('--memory-limit', type=int, default=None,
                       help='内存使用限制（MB，默认系统内存的80%%）')
    parser.add_argument('--max-duration', type=int, default=30,
                       help='每个连接的最大持续时间（秒，默认30）')
    parser.add_argument('--threshold', type=float, default=50.0,
                       help='资源增长阈值（百分比），超过此值认为可能有挖矿脚本（默认50%%）')
    
    args = parser.parse_args()
    
    # 生成输出文件名（保存到results文件夹）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not args.output:
        args.output = os.path.join('results', f'check_results_{timestamp}.json')
    else:
        # 如果指定了路径，确保目录存在
        output_dir = os.path.dirname(args.output) if os.path.dirname(args.output) else 'results'
        os.makedirs(output_dir, exist_ok=True)
        if not os.path.dirname(args.output):
            args.output = os.path.join('results', args.output)
    
    if not args.report:
        args.report = os.path.join('results', f'report_{timestamp}.txt')
    else:
        report_dir = os.path.dirname(args.report) if os.path.dirname(args.report) else 'results'
        os.makedirs(report_dir, exist_ok=True)
        if not os.path.dirname(args.report):
            args.report = os.path.join('results', args.report)
    
    if not args.list:
        args.list = os.path.join('results', f'valid_sites_{timestamp}.txt')
    else:
        list_dir = os.path.dirname(args.list) if os.path.dirname(args.list) else 'results'
        os.makedirs(list_dir, exist_ok=True)
        if not os.path.dirname(args.list):
            args.list = os.path.join('results', args.list)
    
    # 默认使用固定的文件名，所有标记为2的网站都保存到同一个文件
    if not args.mining_list:
        args.mining_list = os.path.join('results', 'mining_sites.txt')
    else:
        mining_list_dir = os.path.dirname(args.mining_list) if os.path.dirname(args.mining_list) else 'results'
        os.makedirs(mining_list_dir, exist_ok=True)
        if not os.path.dirname(args.mining_list):
            args.mining_list = os.path.join('results', args.mining_list)
    
    # 禁用SSL警告
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # 创建检查器
    checker = SiteAccessibilityChecker(
        timeout=args.timeout, 
        max_workers=args.workers,
        cpu_limit_percent=args.cpu_limit,
        memory_limit_mb=args.memory_limit,
        resource_threshold_percent=args.threshold
    )
    
    # 检查网站
    results = checker.check_sites_from_csv(
        args.input, 
        args.output, 
        limit=args.limit,
        max_duration=args.max_duration
    )
    
    # 生成摘要报告
    checker.generate_summary_report(results, args.report)
    
    # 生成可访问网站列表
    checker.generate_valid_sites_list(results, args.list)
    
    # 生成所有标记为2的网站列表（从CSV中读取所有已标记的）
    checker.generate_mining_sites_list(args.input, args.mining_list)
    
    logger.info(f"\n所有输出文件:")
    logger.info(f"  - JSON结果: {args.output}")
    logger.info(f"  - 摘要报告: {args.report}")
    logger.info(f"  - 可访问网站列表: {args.list}")
    logger.info(f"  - 挖矿网站列表（所有标记为2）: {args.mining_list}")
    logger.info(f"  - 日志文件: {log_file}")


if __name__ == "__main__":
    main()

