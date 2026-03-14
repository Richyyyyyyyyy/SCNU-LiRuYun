#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Selenium核心依赖
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException, ElementNotInteractableException,
    ElementClickInterceptedException, NoSuchWindowException
)
from selenium.webdriver.support.expected_conditions import presence_of_element_located

# 驱动管理依赖
from webdriver_manager.firefox import GeckoDriverManager

# 适配不同版本webdriver-manager的Edge驱动命名差异
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager as EdgeDriverManager
except ImportError:
    from webdriver_manager.microsoft import EdgeDriverManager

# 浏览器服务配置
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver import Firefox, FirefoxOptions, Edge, EdgeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.webdriver import WebDriver

# 辅助工具模块
from loguru import logger
from tqdm import tqdm
from time import sleep
from sys import exit, platform
from base64 import b64encode, b64decode
from dataclasses import dataclass
from os import makedirs, path
from typing import List, Tuple

# 全局配置
BROWSER = "firefox"  # 核心配置：指定使用的浏览器(edge/firefox)
PROJECT_ROOT = path.dirname(path.abspath(__file__))  # 项目根目录，统一管理文件路径

# 数据结构定义
@dataclass
class Video:
    """视频数据模型：封装视频名称、URL、播放状态等核心属性"""
    name: str  # 视频名称
    url: str  # 视频播放URL（唯一标识）
    is_finished: bool = False  # 播放完成标记
    index: int = 0  # 视频在课程内的序号

    def __repr__(self):
        """自定义字符串表示，便于日志输出"""
        return f"Video(name={self.name[:10]}..., url={self.url[:20]}..., finished={self.is_finished})"


@dataclass
class Course:
    """课程数据模型：封装课程名称、URL、关联视频列表及完成状态"""
    name: str  # 课程名称
    url: str  # 课程主页URL（唯一标识）
    videos: List[Video]  # 课程下的视频列表
    is_finished: bool = False  # 课程完成标记
    index: int = 0  # 课程在总列表中的序号

    def __repr__(self):
        """自定义字符串表示，便于日志输出"""
        finished_count = sum(1 for v in self.videos if v.is_finished)
        return f"Course(name={self.name[:10]}..., videos={len(self.videos)} (finished={finished_count}), index={self.index})"


# 核心函数定义
def get_web_driver(_mute: bool = True, _show_window: bool = True) -> WebDriver:
    """
    创建并配置WebDriver实例，自动处理驱动下载和跨平台兼容
    Args:
        _mute: 浏览器音频静音（默认True）
        _show_window: 是否显示浏览器窗口（默认True）
    Returns:
        配置完成的WebDriver实例
    Raises:
        SystemExit: 浏览器类型不支持时退出
    """
    _driver = None

    if BROWSER == "edge":
        options = EdgeOptions()
        if _mute:
            options.add_argument("--mute-audio")
        if platform.startswith("linux"):
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-software-rasterizer")
        if not _show_window:
            options.add_argument("--window-position=-2000,-2000")
        # 要改
        service = EdgeService(EdgeDriverManager().install())
        _driver = Edge(options=options, service=service)

    elif BROWSER == "firefox":
        options = FirefoxOptions()
        if _mute:
            options.set_preference("media.volume_scale", "0.0")
        options.set_preference("intl.accept_languages", "zh-CN,zh")
        if platform.startswith("linux"):
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
        if not _show_window:
            options.add_argument("--window-position=-2000,-2000")

        # 要改
        service = FirefoxService(GeckoDriverManager().install())
        _driver = Firefox(options=options, service=service)

    else:
        logger.critical(f"不支持的浏览器类型：{BROWSER} | 仅支持 edge / firefox")
        exit(1)

    _driver.implicitly_wait(10)
    _driver.set_window_size(1280, 720)
    return _driver


def login(_driver: WebDriver, _username: str, _password: str) -> None:
    """
    自动完成Moodle平台SSO统一认证登录
    Args:
        _driver: WebDriver实例
        _username: 统一认证学号
        _password: 统一认证密码
    Raises:
        SystemExit: 登录失败时退出
    """
    logger.info("开始加载Moodle登录页面...")
    _driver.get("https://moodle.scnu.edu.cn/login/index.php")

    try:
        sso_btn = _driver.find_element(By.ID, "ssobtn")
        sso_btn.click()
    except NoSuchElementException:
        logger.critical("未找到SSO登录按钮，页面结构可能变更")
        sleep(10)
        exit(1)

    logger.info("跳转到统一认证页面，输入账号密码...")
    _driver.find_element(By.ID, "account").send_keys(_username)
    _driver.find_element(By.ID, "password").send_keys(_password)
    _driver.find_element(By.ID, "btn-password-login").click()

    try:
        confirm_btn = _driver.find_element(By.LINK_TEXT, "确定登录")
        confirm_btn.click()
    except NoSuchElementException:
        logger.warning("未找到'确定登录'按钮，可能已自动授权")

    try:
        welcome_elem = _driver.find_element(By.CSS_SELECTOR, 'h1.h2.mb-3.mt-3')
        logger.success(f"登录成功！欢迎信息：{welcome_elem.text}")
    except NoSuchElementException:
        logger.critical("登录失败！请检查账号密码或页面结构")
        sleep(10)
        exit(1)


def play_video(
        _driver: WebDriver,
        _video: Video,
        _index_info: str = "",
        _finish_percentage: int = 100
) -> None:
    """
    自动播放单个视频并监控进度，达到阈值后标记为完成
    Args:
        _driver: WebDriver实例
        _video: 待播放的Video对象
        _index_info: 进度日志前缀（如[课程1/5][视频2/10]）
        _finish_percentage: 播放完成阈值（默认100%）
    """

    def truncate_string(s: str, max_length: int = 10) -> str:
        return s[:max_length] + "..." if len(s) > max_length else s

    logger.info(f"{_index_info} 开始播放视频：{_video.name}")
    try:
        _driver.get(_video.url)
    except Exception as e:
        logger.error(f"{_index_info} 视频页面加载失败：{str(e)} | 视频：{_video.name}")
        return

    # 触发不同类型视频播放
    if "h5pactivity" in _video.url:
        try:
            first_iframe = WebDriverWait(_driver, 10).until(presence_of_element_located((By.TAG_NAME, "iframe")))
            _driver.switch_to.frame(first_iframe)
            second_iframe = WebDriverWait(_driver, 10).until(presence_of_element_located((By.TAG_NAME, "iframe")))
            _driver.switch_to.frame(second_iframe)

            play_btn = _driver.find_element(By.CLASS_NAME, "h5p-control.h5p-pause.h5p-play")
            play_btn.click()
            _driver.switch_to.default_content()
        except Exception as e:
            logger.error(f"{_index_info} H5P视频播放操作失败：{str(e)} | 视频：{_video.name}")
            return
    elif "fsresource" in _video.url:
        try:
            play_btn = _driver.find_element(By.CLASS_NAME, "vjs-button-icon")
            play_btn.click()
        except Exception as e:
            logger.error(f"{_index_info} Prism视频播放操作失败：{str(e)} | 视频：{_video.name}")
            return

    # 监控播放进度
    with tqdm(
            total=100,
            desc=f"{_index_info}{truncate_string(_video.name)} 播放进度",
            ncols=100,
            unit="%",
            position=0,
            colour="green"
    ) as pbar:
        while True:
            try:
                if "h5pactivity" in _video.url:
                    progress_elem = _driver.find_element(By.CLASS_NAME, "cell.c3")
                    percentage = float(progress_elem.text.strip('%'))
                else:
                    progress_elem = _driver.find_element(By.CLASS_NAME, "number.num-bfjd")
                    percentage = float(progress_elem.text.strip('%'))

                pbar.n = percentage
                pbar.last_print_n = percentage
                pbar.update(0)

                if percentage >= _finish_percentage:
                    sleep(1)
                    pbar.n = 100.0
                    _video.is_finished = True
                    logger.success(f"{_index_info} 视频播放完成：{_video.name}")
                    break

                sleep(1)
            except Exception as e:
                logger.warning(f"{_index_info} 进度监控中断：{str(e)} | 视频：{_video.name}")
                break


def scrape_course_videos(_driver: WebDriver, _course_url: str) -> List[Video]:
    """
    爬取单个课程下的所有有效视频（H5P/fsresource类型）并去重
    Args:
        _driver: WebDriver实例
        _course_url: 课程主页URL
    Returns:
        去重后的视频列表
    """
    logger.info(f"爬取课程视频：{_course_url}")
    _driver.get(_course_url)

    # 尝试展开侧边栏
    try:
        sleep(2)
        expand_btn = _driver.find_element(By.CLASS_NAME, "drawer-toggler.drawer-left-toggle.open-nav.d-print-none")
        expand_btn.click()
        logger.info("展开课程侧边栏，提取视频链接...")
        sleep(2)
    except Exception as e:
        # logger.warning(f"侧边栏展开失败（可能已展开）：{str(e)}")
        # 好像开了也会弹出，所以就不输出了
        pass

    all_links = _driver.find_elements(By.TAG_NAME, "a")
    raw_videos = []
    for link in all_links:
        try:
            link_url = str(link.get_attribute("href")).strip()
            link_name = str(link.text).strip()
            if link_url and link_name and "资源库文件" not in link_name:
                if "h5pactivity/view.php" in link_url or "fsresource/view.php" in link_url:
                    raw_videos.append(Video(name=link_name, url=link_url))
        except Exception as e:
            logger.debug(f"链接提取失败：{str(e)} | 跳过该链接")
            continue

    # 去重
    unique_videos = []
    seen_urls = set()
    for video in raw_videos:
        if video.url not in seen_urls:
            seen_urls.add(video.url)
            unique_videos.append(video)

    # 分配序号
    for idx, video in enumerate(unique_videos, start=1):
        video.index = idx

    logger.info(f"课程视频爬取完成：{len(unique_videos)} 个有效视频")
    return unique_videos


def get_user_info() -> Tuple[str, str]:
    """
    获取用户账号密码（优先读取本地Base64加密缓存，无则手动输入并保存）
    Returns:
        (学号, 密码)
    """
    user_cfg_path = path.join(PROJECT_ROOT, "user.cfg")

    def input_and_save():
        BROWSER = input("\n请输入你选择的浏览器[ edge | firefox ]: ")
        username = input("请输入统一认证学号：").strip()
        password = input("请输入统一认证密码：").strip()
        if not username or not password or not BROWSER:
            logger.error("账号/密码/浏览器不能为空！")
            return input_and_save()

        makedirs(path.dirname(user_cfg_path), exist_ok=True)
        encoded = b64encode(str((username, password, BROWSER)).encode()).decode()
        with open(user_cfg_path, "w", encoding="utf-8") as f:
            f.write(encoded)
        logger.success("账号密码已保存至本地（Base64编码）")
        return username, password

    try:
        with open(user_cfg_path, "r", encoding="utf-8") as f:
            encoded = f.read().strip()
        username, password, BROWSER = eval(b64decode(encoded).decode())
        logger.info(f"读取本地缓存账号：{username}")

        update = input("是否更新账号密码？[Y/任意键否]：").strip().upper()
        if update == "Y":
            return input_and_save()
        return username, password
    except (FileNotFoundError, SyntaxError, NameError):
        logger.info("未找到本地账号缓存，手动输入...")
        return input_and_save()


def scrape_courses(_driver: WebDriver) -> List[Course]:
    """
    爬取"我的课程"列表（仅保留包含视频的课程）
    Args:
        _driver: 已登录的WebDriver实例
    Returns:
        有效课程列表
    """
    logger.info("爬取'我的课程'列表...")
    try:
        course_menu = _driver.find_element(By.CLASS_NAME, "dropdown.nav-item.mycourse")
        course_links = course_menu.find_elements(By.TAG_NAME, "a")
    except NoSuchElementException:
        logger.critical("未找到'我的课程'菜单，页面结构可能变更")
        return []

    raw_courses = []
    for link in course_links:
        try:
            course_url = str(link.get_attribute("href")).strip()
            course_name = str(link.get_attribute("title")).strip()
            if course_url and "course/view.php" in course_url and course_name:
                raw_courses.append(Course(name=course_name, url=course_url, videos=[]))
        except Exception as e:
            logger.debug(f"课程提取失败：{str(e)} | 跳过该课程")
            continue

    # 过滤有视频的课程
    valid_courses = []
    for course in raw_courses:
        logger.info(f"处理课程：{course.name}")
        course.videos = scrape_course_videos(_driver, course.url)
        if course.videos:
            valid_courses.append(course)

    # 分配课程序号
    for idx, course in enumerate(valid_courses, start=1):
        course.index = idx

    total_videos = sum(len(course.videos) for course in valid_courses)
    logger.success(f"课程爬取完成：{len(valid_courses)} 个有效课程，总视频 {total_videos} 个")
    return valid_courses


def play_all_videos(_driver: WebDriver, _courses: List[Course]) -> None:
    """
    批量播放所有课程的未完成视频，按课程→视频顺序循环
    Args:
        _driver: WebDriver实例
        _courses: 课程列表
    """
    logger.info("开始批量播放未完成视频...")
    while True:
        all_courses_finished = True

        for course in _courses:
            if course.is_finished:
                logger.info(f"课程 {course.name} 已完成，跳过")
                continue

            all_courses_finished = False
            logger.info(f"\n===== 处理课程 [{course.index}/{len(_courses)}]：{course.name} =====")

            course_finished = True
            for video in course.videos:
                if not video.is_finished:
                    course_finished = False
                    index_prefix = f"[课程{course.index}/{len(_courses)}][视频{video.index}/{len(course.videos)}]"
                    play_video(_driver, video, index_prefix)

            course.is_finished = course_finished
            if course_finished:
                logger.success(f"课程 {course.name} 所有视频已完成！")

        if all_courses_finished:
            logger.success("所有课程视频均已播放完成！")
            break


def save_courses(user: str, courses: List[Course]) -> None:
    """保存课程/视频进度到本地缓存（Base64加密）"""
    cache_dir = path.join(PROJECT_ROOT, "cache")
    makedirs(cache_dir, exist_ok=True)
    cache_file = path.join(cache_dir, user)

    try:
        encoded = b64encode(str(courses).encode()).decode()
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(encoded)
        logger.success("课程进度已保存至本地缓存")
    except Exception as e:
        logger.error(f"缓存保存失败：{str(e)}")


def get_courses(_driver: WebDriver, _user: str) -> List[Course]:
    """
    获取课程列表（优先读取本地缓存，支持手动重新爬取）
    Args:
        _driver: 已登录的WebDriver实例
        _user: 学号（缓存文件名）
    Returns:
        课程列表（含缓存进度或新爬取数据）
    """
    cache_file = path.join(PROJECT_ROOT, "cache", _user)

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            encoded = f.read().strip()
        courses = eval(b64decode(encoded).decode())
        logger.info("读取本地课程缓存成功")

        re_scrape = input("是否重新爬取课程列表？[Y/任意键否]：").strip().upper()
        if re_scrape == "Y":
            courses = scrape_courses(_driver)
    except (FileNotFoundError, SyntaxError, NameError):
        logger.info("本地课程缓存不存在/解析失败，重新爬取...")
        courses = scrape_courses(_driver)

    save_courses(_user, courses)
    return courses


# 主程序入口
if __name__ == "__main__":
    driver = None
    courses = []
    username = ""

    try:
        # 日志配置
        log_dir = path.join(PROJECT_ROOT, "log")
        makedirs(log_dir, exist_ok=True)
        logger.add(
            path.join(log_dir, "run.log"),
            rotation="1MB",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True
        )
        logger.success(f"程序启动 | 系统：{platform}")
        # 核心执行流程
        username, password = get_user_info()
        driver = get_web_driver()
        login(driver, username, password)
        courses = get_courses(driver, username)
        play_all_videos(driver, courses)

    except NoSuchWindowException:
        logger.critical("程序中断：浏览器窗口被手动关闭")
    except KeyboardInterrupt:
        logger.critical("程序中断：用户手动终止（Ctrl+C）")
    except Exception as e:
        logger.exception(f"程序异常终止：{str(e)}")
    finally:
        # 收尾操作
        if driver:
            logger.info("关闭浏览器窗口...")
            driver.quit()
        if username and courses:
            save_courses(username, courses)
        logger.success("程序正常退出")
