from selenium.webdriver import Edge, EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, ElementClickInterceptedException, NoSuchWindowException, TimeoutException
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from loguru import logger
from tqdm import tqdm
from time import sleep
from sys import exit
from base64 import b64encode, b64decode
from dataclasses import dataclass, asdict
from os import makedirs, remove
from os.path import dirname, exists
import json


@dataclass
class Video:
    name: str
    url: str
    is_finished: bool = False
    index: int = 0


@dataclass
class Course:
    name: str
    url: str
    videos: list[Video]
    is_finished: bool = False
    index: int = 0


def get_web_driver(_mute: bool = True, _show_window: bool = True) -> WebDriver:
    options = EdgeOptions()
    if _mute:
        options.add_argument("--mute-audio")
    
    # 添加更多选项提高稳定性
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 使用 Service 对象来初始化 Edge 驱动
    try:
        # 新版本 Selenium 的初始化方式
        service = EdgeService()
        _driver = Edge(service=service, options=options)
    except TypeError:
        # 如果上面的方式失败，回退到旧版本方式
        try:
            _driver = Edge(options=options)
        except Exception as e:
            logger.error(f"初始化浏览器失败: {e}")
            # 最后尝试无参初始化
            _driver = Edge()

    # 伪无头模式
    if not _show_window:
        _driver.set_window_position(-2000, -2000)

    # 超时等待时间
    _driver.implicitly_wait(10)

    return _driver


def login(_driver: WebDriver, _username: str, _password: str) -> None:
    try:
        # 跳转到综合平台
        logger.info("正在加载登陆界面...")
        _driver.get("https://moodle.scnu.edu.cn/login/index.php")
        
        # 等待页面加载
        sleep(2)
        _driver.find_element(By.ID, "ssobtn").click()

        # 登录到砺儒云
        logger.info("正在登陆...")
        WebDriverWait(_driver, 10).until(presence_of_element_located((By.ID, "account"))).send_keys(_username)
        _driver.find_element(By.ID, "password").send_keys(_password)
        _driver.find_element(By.ID, "btn-password-login").click()
        
        # 等待并点击确定登录
        sleep(3)
        _driver.find_element(By.LINK_TEXT, "确定登录").click()

        # 确定是否成功登录
        try:
            h1_element = WebDriverWait(_driver, 10).until(
                presence_of_element_located((By.CSS_SELECTOR, 'h1.h2.mb-3.mt-3'))
            )
            logger.info(f"登陆成功! {h1_element.text}")
        except (NoSuchElementException, TimeoutException):
            logger.critical("登陆失败!请检查页面和账号密码")
            sleep(10)
            exit(1)
            
    except Exception as e:
        logger.error(f"登录过程中出现错误: {e}")
        exit(1)


def play_video(_driver: WebDriver, _video: Video, _index_info: str = "", _finish_percentage: int = 93) -> None:  # 修改默认完成阈值为93%
    # 压缩字符串的方法
    def truncate_string(s: str, max_length: int = 10) -> str:
        if len(s) > max_length:
            return s[:max_length] + "..."
        else:
            return s

    # 播放视频
    logger.info(f"{_index_info}视频->{_video.name}正在播放")
    try:
        _driver.get(_video.url)
        sleep(3)  # 等待页面加载
    except Exception as e:
        logger.error(f"当前视频页面加载出现问题: {e}")
        return
        
    # 根据链接对播放器进行适配
    if "h5pactivity" in _video.url:
        try:
            # 切换到第一个 iframe
            first_iframe = WebDriverWait(_driver, 10).until(presence_of_element_located((By.TAG_NAME, "iframe")))
            _driver.switch_to.frame(first_iframe)

            # 切换到第二个 iframe
            second_iframe = WebDriverWait(_driver, 10).until(presence_of_element_located((By.TAG_NAME, "iframe")))
            _driver.switch_to.frame(second_iframe)

            # 点击播放按钮
            try:
                play_button = WebDriverWait(_driver, 10).until(
                    presence_of_element_located((By.CLASS_NAME, "h5p-control.h5p-pause.h5p-play"))
                )
                play_button.click()
            except (NoSuchElementException, ElementNotInteractableException, TimeoutException):
                logger.error(f"页面元素处理出错: {_video.name}")
                _driver.switch_to.default_content()
                return

            # 切换到主界面
            _driver.switch_to.default_content()

        except Exception as e:
            logger.error(f"处理h5pactivity视频时出错: {e}")
            _driver.switch_to.default_content()
            return

    else:
        # 点击播放按钮
        try:
            play_button = WebDriverWait(_driver, 10).until(
                presence_of_element_located((By.CLASS_NAME, "prism-big-play-btn"))
            )
            play_button.click()
        except (NoSuchElementException, ElementNotInteractableException, TimeoutException):
            logger.error(f"页面元素处理出错: {_video.name}")
            return

    # 检查播放进度
    with tqdm(total=100, desc=f"{_index_info}{truncate_string(_video.name)}播放进度", ncols=100, unit="%", position=0) as pbar:
        last_percentage = 0
        no_progress_count = 0
        # 调整无进度检测参数，因为查询频率降低了
        max_no_progress = 30  # 如果30次查询没有进度，认为卡住（原本是60秒，现在调整为10秒/2秒一次）
        
        while True:
            try:
                # 获取进度百分比
                if "h5pactivity" in _video.url:
                    # 切换到主页面来查找表格
                    _driver.switch_to.default_content()
                    
                    # 查找包含进度信息的表格
                    try:
                        # 首先尝试查找整个表格
                        table = _driver.find_element(By.CLASS_NAME, "generaltable.cell-border.report_h5pstats_h5pactivity_table")
                        
                        # 在表格中查找进度百分比（"cell c3"）
                        percentage_element = table.find_element(By.CLASS_NAME, "cell.c3")
                        percentage_text = percentage_element.text.strip('%')
                        percentage = float(percentage_text) if percentage_text else 0
                        
                        logger.debug(f"从表格中获取进度: {percentage}%")
                        
                    except NoSuchElementException:
                        # 如果找不到表格，可能是页面结构不同，尝试其他方式
                        logger.debug("未找到进度表格，尝试其他方式...")
                        
                        # 尝试直接查找进度元素
                        try:
                            percentage_element = _driver.find_element(By.CSS_SELECTOR, "td.cell.c3")
                            percentage_text = percentage_element.text.strip('%')
                            percentage = float(percentage_text) if percentage_text else 0
                            logger.debug(f"直接查找进度元素: {percentage}%")
                        except NoSuchElementException:
                            logger.debug("无法找到进度元素，返回0%")
                            percentage = 0
                    
                else:
                    # 保持原有的非h5pactivity视频进度获取方式不变
                    try:
                        percentage_text = _driver.find_element(By.CLASS_NAME, "number.num-bfjd").text.strip('%')
                        percentage = float(percentage_text) if percentage_text else 0
                    except NoSuchElementException:
                        # 尝试其他可能的选择器
                        try:
                            percentage_text = _driver.find_element(By.CLASS_NAME, "prism-progress-text").text.strip('%')
                            percentage = float(percentage_text) if percentage_text else 0
                        except NoSuchElementException:
                            percentage = 0

                # 更新进度条
                pbar.n = percentage
                pbar.last_print_n = percentage
                pbar.update(0)

                # 检查是否卡住
                if percentage <= last_percentage:
                    no_progress_count += 1
                else:
                    no_progress_count = 0
                    last_percentage = percentage

                if no_progress_count >= max_no_progress:
                    logger.warning(f"视频进度卡住，跳过: {_video.name}")
                    break

                # 修改：当进度大于等于93%时，视为已完成
                if percentage >= _finish_percentage:
                    sleep(1)
                    pbar.n = 100.00
                    pbar.last_print_n = 100.00
                    pbar.update(0)
                    _video.is_finished = True
                    logger.info(f"{_index_info}视频->{_video.name}播放完成（达到{percentage}%，超过{_finish_percentage}%阈值）")
                    break
                
                # 根据当前进度决定下次查询的间隔时间
                if percentage >= 95:
                    # 进度大于95%时，每2秒查询一次
                    sleep_time = 2
                else:
                    # 进度小于95%时，每10秒查询一次
                    sleep_time = 10
                
                sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"获取进度时出错: {e}")
                # 出错时也根据当前进度决定等待时间
                if last_percentage >= 95:
                    sleep_time = 2
                else:
                    sleep_time = 10
                sleep(sleep_time)
                no_progress_count += 1
                if no_progress_count >= max_no_progress:
                    logger.warning(f"多次获取进度失败，跳过: {_video.name}")
                    break


def scrape_course_videos(_driver: WebDriver, _course_url: str) -> list[Video]:
    try:
        # 访问课程页面
        logger.info("正在进入课程页面...")
        _driver.get(_course_url)
        sleep(3)

        # 展开课程列表
        try:
            logger.info("正在检测页面状态...")
            btn_open = _driver.find_element(By.CLASS_NAME, "drawer-toggler.drawer-left-toggle.open-nav.d-print-none")
            btn_open.click()
            logger.info("正在展开课程列表...")
            sleep(2)
        except (ElementNotInteractableException, ElementClickInterceptedException, NoSuchElementException):
            logger.info("课程列表已展开或无需展开")

        # 爬取视频链接
        logger.info("正在爬取视频链接...")
        links = _driver.find_elements(By.TAG_NAME, "a")
        _videos: list[Video] = []
        
        for link in links:
            try:
                url = str(link.get_attribute("href") or "")
                name = link.text.strip()
                if ("https://moodle.scnu.edu.cn/mod/h5pactivity/view.php" in url) or ("https://moodle.scnu.edu.cn/mod/fsresource/view.php" in url):
                    if name:  # 只添加有名称的视频
                        _videos.append(Video(name, url))
            except Exception as e:
                logger.debug(f"处理链接时出错: {e}")
                continue

        # 链接去重
        seen_urls = set()
        unique_videos = []
        for video in _videos:
            if video.url not in seen_urls and ("资源库文件" not in video.name) and video.name:
                seen_urls.add(video.url)
                unique_videos.append(video)

        # 为索引赋值
        for i, video in enumerate(unique_videos, 1):
            video.index = i

        logger.info(f"共计找到{len(unique_videos)}个视频")
        return unique_videos
        
    except Exception as e:
        logger.error(f"爬取课程视频时出错: {e}")
        return []


def get_user_info() -> tuple[str, str]:
    def ask_for_user_info() -> tuple[str, str]:
        __username = input("请键入统一认证登录学号: ")
        __password = input("请键入统一认证登录密码: ")
        user_info = {"username": __username, "password": __password}
        makedirs(dirname("./user.cfg"), exist_ok=True)
        with open("./user.cfg", "w", encoding='utf-8') as file:
            file.write(b64encode(json.dumps(user_info).encode()).decode())
        logger.info("统一认证登录学号与密码已存储至user.cfg")
        return (__username, __password)

    try:
        logger.info("正在获取统一认证登录学号和密码...")
        if exists("./user.cfg"):
            with open("./user.cfg", "r", encoding='utf-8') as file:
                user_info = json.loads(b64decode(file.read()).decode())
                _username, _password = user_info["username"], user_info["password"]
            
            logger.info(f"当前账户为{_username}")
            if input("是否需要更新学号或密码,需要请输入'Y',不需要请输入任意值[Y/任意值]: ") == "Y":
                _username, _password = ask_for_user_info()
                logger.info(f"当前账户为{_username}")
        else:
            _username, _password = ask_for_user_info()
            
    except Exception as e:
        logger.error(f"读取用户信息时出错: {e}")
        _username, _password = ask_for_user_info()
    
    return (_username, _password)


def scrape_courses(_driver: WebDriver) -> list[Course]:
    try:
        # 获取超链接
        parent_element = _driver.find_element(By.CLASS_NAME, "dropdown.nav-item.mycourse")
        links = parent_element.find_elements(By.TAG_NAME, "a")

        _courses: list[Course] = []
        for link in links:
            try:
                url = str(link.get_attribute("href") or "")
                name = str(link.get_attribute("title") or "")
                # 修改：只保留指定课程 (id=18208)
                if url == "https://moodle.scnu.edu.cn/course/view.php?id=18208" and name:
                    _courses.append(Course(name, url, []))
                    logger.info(f"找到目标课程: {name}")
                else:
                    # 跳过其他所有课程
                    continue
            except Exception as e:
                logger.debug(f"处理课程链接时出错: {e}")
                continue
                
        logger.info(f"共计找到{len(_courses)}个课程")

        # 爬取视频
        valid_courses = []
        for i, course in enumerate(_courses):
            try:
                logger.info(f"正在爬取课程[{i+1}/{len(_courses)}]{course.name}的视频")
                course_videos = scrape_course_videos(_driver, course.url)
                if course_videos:
                    course.videos = course_videos
                    valid_courses.append(course)
                else:
                    logger.warning(f"课程{course.name}没有找到视频，已跳过")
            except Exception as e:
                logger.error(f"爬取课程{course.name}的视频时出错: {e}")
                continue

        # 为索引赋值
        for i, course in enumerate(valid_courses, 1):
            course.index = i

        logger.info(f"发现了{len(valid_courses)}个需要观看的课程中的{sum(len(course.videos) for course in valid_courses)}个视频")
        return valid_courses
        
    except Exception as e:
        logger.error(f"爬取课程列表时出错: {e}")
        return []


def play_all_videos(_driver: WebDriver, _courses: list[Course]) -> None:
    max_retries = 3
    
    for _course in _courses:
        if not _course.is_finished:
            logger.info(f"[{_course.index}/{len(_courses)}]课程->{_course.name}正在播放")
            
            for _video in _course.videos:
                if not _video.is_finished:
                    retry_count = 0
                    while retry_count < max_retries and not _video.is_finished:
                        index_info = f"[{_course.index}/{len(_courses)}][{_video.index}/{len(_course.videos)}]"
                        try:
                            play_video(_driver, _video, index_info)
                        except Exception as e:
                            logger.error(f"播放视频失败: {e}")
                            retry_count += 1
                            sleep(5)  # 等待后重试
            
            # 检查课程是否完成
            finished_count = sum(1 for video in _course.videos if video.is_finished)
            if finished_count == len(_course.videos):
                _course.is_finished = True
                logger.info(f"课程->{_course.name}所有视频已完成")


def save_courses(_username: str, _courses: list[Course]) -> None:
    try:
        makedirs(dirname(f"./cache/"), exist_ok=True)
        # 转换为可序列化的字典
        courses_data = []
        for course in _courses:
            course_dict = asdict(course)
            course_dict['videos'] = [asdict(video) for video in course.videos]
            courses_data.append(course_dict)
            
        with open(f"./cache/{_username}", "w", encoding='utf-8') as file:
            file.write(b64encode(json.dumps(courses_data).encode()).decode())
        logger.info(f"缓存数据已存储至./cache/{_username}")
    except Exception as e:
        logger.error(f"保存课程数据时出错: {e}")


def get_courses(_driver: WebDriver, _username: str) -> list[Course]:
    def dict_to_course(course_dict: dict) -> Course:
        videos = [Video(**video_data) for video_data in course_dict.get('videos', [])]
        return Course(
            name=course_dict['name'],
            url=course_dict['url'],
            videos=videos,
            is_finished=course_dict.get('is_finished', False),
            index=course_dict.get('index', 0)
        )

    cache_file = f"./cache/{_username}"
    try:
        if exists(cache_file):
            with open(cache_file, "r", encoding='utf-8') as file:
                logger.info("正在获取缓存数据")
                courses_data = json.loads(b64decode(file.read()).decode())
                _courses = [dict_to_course(course_data) for course_data in courses_data]
  
            logger.info(f"从缓存发现了{len(_courses)}个需要观看的课程中的{sum(len(course.videos) for course in _courses)}个视频")
            if input("是否需要刷新数据，需要请输入'Y',不需要请输入任意值[Y/任意值]: ") == "Y":
                _courses = scrape_courses(_driver)
        else:
            logger.info("未找到缓存数据")
            _courses = scrape_courses(_driver)

        save_courses(_username, _courses)
        return _courses
        
    except Exception as e:
        logger.error(f"读取缓存数据时出错: {e}")
        _courses = scrape_courses(_driver)
        save_courses(_username, _courses)
        return _courses


if __name__ == "__main__":
    """
    已经通过测试的课程:
    四史
    中华民族共同体概论
    大学生劳动教育理论与实践
    大学生心理健康教育
    """
    driver = None
    courses = []
    
    try:
        # 配置日志
        makedirs("./log", exist_ok=True)
        logger.add("./log/run.log", rotation="1 MB", compression="zip", encoding='utf-8')
        logger.info("启动程序")

        # 获取用户名和密码
        username, password = get_user_info()

        # 实例化浏览器
        driver = get_web_driver()

        # 登录到砺儒云平台
        login(driver, username, password)

        # 获取视频数据
        courses = get_courses(driver, username)

        if not courses:
            logger.warning("没有找到需要观看的课程")
        else:
            # 逐个播放网课视频
            play_all_videos(driver, courses)
            logger.info("所有视频播放完成")
    
    except NoSuchWindowException:
        logger.critical("浏览器窗口被关闭")
    
    except KeyboardInterrupt:
        logger.info("用户中断程序执行")
    
    except Exception as ex:
        logger.exception(f"发生了一个意料之外的错误: {ex}")
    
    finally:
        try: 
            if driver:
                driver.quit()
                logger.info("浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器时出错: {e}")
            
        try: 
            if courses:
                save_courses(username, courses)  # type: ignore
        except Exception as e:
            logger.error(f"保存课程数据时出错: {e}")
            
        logger.info("退出程序")