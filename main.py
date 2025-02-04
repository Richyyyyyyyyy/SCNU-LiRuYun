from selenium.webdriver import Edge, EdgeOptions
from selenium.webdriver.edge.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, ElementClickInterceptedException, NoSuchWindowException
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from loguru import logger
from tqdm import tqdm
from time import sleep
from sys import exit
from base64 import b64encode, b64decode
from dataclasses import dataclass
from os import makedirs
from os.path import dirname


@dataclass
class Video:
    name:str
    url:str
    is_finished:bool = False
    index:int = 0


@dataclass
class Course:
    name:str
    url:str
    videos:list[Video]
    is_finished:bool = False
    index:int = 0

def get_web_driver(_mute:bool=True, _show_window:bool=True) -> WebDriver:
    options = EdgeOptions()
    if _mute:
        options.add_argument("--mute-audio")
    _driver = Edge(options)

    # 伪无头模式
    if not _show_window:
        _driver.set_window_position(-2000, -2000)

    # 超时等待时间
    _driver.implicitly_wait(10)

    return _driver


def login(_driver:WebDriver, _username:str, _password:str) -> None:

    # 跳转到综合平台
    logger.info("正在加载登陆界面...")
    _driver.get("https://moodle.scnu.edu.cn/login/index.php")
    _driver.find_element(By.ID, "ssobtn").click()

    # 登录到砺儒云
    logger.info("正在登陆...")
    _driver.find_element(By.ID, "account").send_keys(_username)
    _driver.find_element(By.ID, "password").send_keys(_password)
    _driver.find_element(By.ID, "btn-password-login").click()
    _driver.find_element(By.LINK_TEXT, "确定登录").click()

    # 确定是否成功登录
    try:
        h1_element = _driver.find_element(By.CSS_SELECTOR, 'h1.h2.mb-3.mt-3')
        logger.info("登陆成功!", h1_element.text)
    except NoSuchElementException:
        logger.critical("登陆失败!请检查页面和账号密码")
        sleep(10)
        exit(1)


def play_video(_driver:WebDriver, _video:Video, _index_info:str="", _finish_percentage:int=100) -> None:

    # 压缩字符串的方法
    def truncate_string(s:str, max_length:int=10) -> str:
        if len(s) > max_length:
            return s[:max_length] + "..."
        else:
            return s

    # 播放视频
    logger.info(f"{_index_info}视频->{_video.name}正在播放")
    try:
        _driver.get(_video.url)
    except Exception as e:
        logger.error("当前视频页面加载出现问题:", e)
        return
        
    # 根据链接对播放器进行适配
    if "h5pactivity" in _video.url:
        # 切换到第一个 iframe
        first_iframe = WebDriverWait(_driver, 10).until(presence_of_element_located((By.TAG_NAME, "iframe")))
        _driver.switch_to.frame(first_iframe)

        # 切换到第二个 iframe
        second_iframe = WebDriverWait(_driver, 10).until(presence_of_element_located((By.TAG_NAME, "iframe")))
        _driver.switch_to.frame(second_iframe)

        # 点击播放按钮
        try:
            _driver.find_element(By.CLASS_NAME, "h5p-control.h5p-pause.h5p-play").click()
        except NoSuchElementException and ElementNotInteractableException:
            logger.error("页面元素处理出错:", _video.name)
            return

        # 切换到主界面
        _driver.switch_to.default_content()

    else:
        # 点击播放按钮
        try:
            driver.find_element(By.CLASS_NAME, "prism-big-play-btn").click()
        except NoSuchElementException and ElementNotInteractableException:
            logger.error(f"页面元素处理出错:{_video.name}")
            return

        # 检查播放进度
    with tqdm(total=100, desc=f"{_index_info}{truncate_string(_video.name)}播放进度", ncols=100, unit="%", position=0) as pbar:
        while True:
            # 获取进度百分比
            if "h5pactivity" in _video.url:
                percentage = float(_driver.find_element(By.CLASS_NAME, "cell.c3").text.strip('%'))
            else:
                percentage = float(_driver.find_element(By.CLASS_NAME, "number.num-bfjd").text.strip('%'))

            # if percentage != percentage_value:
            # 更新进度条
            percentage_value = percentage
            pbar.n = percentage_value
            pbar.last_print_n = percentage_value
            pbar.update(0)

            # 如果进度超过既定完成进度，则退出
            if percentage_value >= _finish_percentage:
                sleep(1)
                pbar.n = 100.00
                pbar.last_print_n = 100.00
                pbar.update(0)
                _video.is_finished = True
                logger.info(f"{_index_info}视频->{_video.name}播放完成")
                break
            else:
                sleep(1)


def scrape_course_videos(_driver:WebDriver, _course_url:str) -> list[Video]:

    # 访问课程页面
    logger.info("正在进入课程页面...")
    _driver.get(_course_url)

    # 展开课程列表
    try:
        logger.info("正在检测页面状态...")
        _driver.implicitly_wait(2)
        btn_open = _driver.find_element(By.CLASS_NAME, "drawer-toggler.drawer-left-toggle.open-nav.d-print-none")
        btn_open.click()
        logger.info("正在展开课程列表...")
        sleep(2)
    except ElementNotInteractableException or ElementClickInterceptedException:
        pass

    # 爬取视频链接
    _driver.implicitly_wait(10)
    logger.info("正在爬取视频链接...")
    links = _driver.find_elements(By.TAG_NAME, "a")
    _videos:list[Video] = []
    for link in links:
        url = str(link.get_attribute("href"))
        name = link.text
        if ("https://moodle.scnu.edu.cn/mod/h5pactivity/view.php" in url) or ("https://moodle.scnu.edu.cn/mod/fsresource/view.php" in url):
            _videos.append(Video(name, url))

    # 链接去重
    for i in range(len(_videos)-1, -1, -1):
        if ("资源库文件" in _videos[i].name) or (_videos[i].name == ""):
            _videos.pop(i)

    # 为索引赋值
    for i in range(len(_videos)):
         _videos[i].index = i+1

    logger.info(f"共计找到{len(_videos)}个视频")
    return _videos


def get_user_info() -> tuple[str,str]:
    def ask_for_user_info() -> tuple[str,str]:
        __username = input("请键入统一认证登录学号:")
        __password = input("请键入统一认证登录密码:")
        with open("./user.cfg", "w") as file:
            file.write(f"{b64encode(str((__username,__password)).encode())}")
        logger.info("统一认证登录学号与密码已存储至user.cfg")
        return (__username, __password)

    try:
        logger.info("正在获取统一认证登录学号和密码...")
        with open("./user.cfg", "r") as file:
            _username, _password= eval(b64decode(eval(file.read())))
        
        logger.info(f"当前账户为{_username}")
        if input("是否需要更新学号或密码,需要请输入'Y',不需要请输入任意值[Y/任意值]") == "Y":
            _username, _password = ask_for_user_info()
            logger.info(f"当前账户为{_username}")
            
    except FileNotFoundError:
        logger.info("未找到用户信息文件")
        _username, _password = ask_for_user_info()
        logger.info(f"当前账户为{_username}")
    
    return (_username, _password)


def scrape_courses(_driver:WebDriver) -> list[Course]:

    # 获取超链接
    parent_element = _driver.find_element(By.CLASS_NAME, "dropdown.nav-item.mycourse")
    links = parent_element.find_elements(By.TAG_NAME, "a")

    _courses:list[Course] = []
    for link in links:
        url = str(link.get_attribute("href"))
        name = str(link.get_attribute("title"))
        # 过滤
        if "https://moodle.scnu.edu.cn/course/view.php" in url:
            _courses.append(Course(name, url, []))
    logger.info(f"共计找到{len(_courses)}个课程")

    # 爬取视频
    for i in range(len(_courses)-1, -1, -1):
        logger.info(f"正在爬取课程{_courses[i].name}的视频")
        _courses[i].videos = scrape_course_videos(_driver, _courses[i].url)
        if _courses[i].videos == []:
            _courses.pop(i)
    # 为索引赋值
    for i in range(len(_courses)):
         _courses[i].index = i+1

    logger.info(f"发现了{len(_courses)}个需要观看的课程中的{sum(len(_course.videos) for _course in _courses)}个视频")
    return _courses


def play_all_videos(_driver:WebDriver, _courses:list[Course]) -> None:

    # 播放未完成的课程
    for _course in _courses:
        if not _course.is_finished:
            logger.info(f"[{_course.index}/{len(_courses)}]课程->{_course.name}正在播放")
            for _video in _course.videos:
                if not _video.is_finished:
                    index_info = f"[{_course.index}/{len(_courses)}][{_video.index}/{len(_course.videos)}]"
                    play_video(_driver, _video,index_info)
            # 判断课程视频是否全部完成
            if sum(_video.is_finished for _video in _course.videos) == len(_course.videos):
                _course.is_finished = True
            else:
                play_all_videos(_driver, _courses)


def save_courses(_username, _courses) -> None:
    makedirs(dirname(f"./cache/"), exist_ok=True)
    with open(f"./cache/{_username}", "w") as file:
        file.write(f"{b64encode(str(_courses).encode())}")
    logger.info(f"缓存数据已存储至./{_username}.data")


def get_courses(_driver, _username) -> list[Course]:
    try:
        with open(f"./cache/{_username}", "r") as file:
            logger.info("正在获取缓存数据")
            _courses = eval(b64decode(eval(file.read())))
  
        logger.info(f"发现了{len(_courses)}个需要观看的课程中的{sum(len(_course.videos) for _course in _courses)}个视频")
        if input("是否需要刷新数据，需要请输入'Y',不需要请输入任意值[Y/任意值]") == "Y":
            _courses = scrape_courses(_driver)
        
    except FileNotFoundError:
        logger.info("未找到缓存数据")
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
    try:
        # 配置日志
        logger.add("./log/run.log", rotation="1 MB", compression="zip")
        logger.info("启动程序")

        # 获取用户名和密码
        username, password = get_user_info()

        # 实例化浏览器
        driver = get_web_driver()

        # 登录到砺儒云平台
        login(driver, username, password)

        # 获取视频数据
        courses = get_courses(driver, username)

        # 逐个播放网课视频
        play_all_videos(driver, courses)
    
    except NoSuchWindowException:
        logger.critical("浏览器窗口被关闭")
    
    except Exception as ex:
        logger.exception("发生了一个意料之外的错误:", ex)
    
    finally:
        try: driver.quit()                                      # type: ignore
        except NameError: pass
        try: save_courses(username, courses) # type: ignore
        except NameError: pass
        logger.info("退出程序")