import concurrent.futures
import json
import logging
import os
import pathlib
import re
import sys
from os import path
from random import randint
from threading import Thread
from time import sleep
from typing import Dict, List

import requests
import urllib3
from configuration.config import Config
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from requests.adapters import HTTPAdapter
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

from ui.colors import welcome

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("moodle_scraper")
# save logs to file
logging.basicConfig(filename='moodle_scraper.log', level=logging.INFO)
# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
# add formatter to ch
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

HTML_EXT = ".html"
HTML_PARSER = "html.parser"

config = json.load(open('scraper.json'))
USERNAME = config['user']
PASSWORD = config['pwd']
BASEURL = config['baseurl']
DIRECTORY = config['directory']
# This is optional and will fix corner cases where the home page is not the login page (e.g. CAS)
LOGIN_URL = config.get('login_url', None)


class Downloader:
    def __init__(self, debugging=False):
        self.username = USERNAME
        self.password = PASSWORD
        self.directory = DIRECTORY
        self.moodle_url: str = BASEURL
        # None: use the default moodle login page; otherwise, use the specified login page (e.g. the specific CAS page)
        self.login_url: str = LOGIN_URL
        self.config: Config = Config()
        self.threads_list: List[Thread] = []
        self.session = None
        self.courses: Dict[str, str] = {}
        self.files: Dict[str, Dict[str, str]] = {}
        self.paragraphs: Dict[str, List[str]] = {}
        self.pool_size: int = 0
        self.save_path: str = ""
        self.course_paths_list: List[str] = []
        self.wait_time: int = 0
        # This will skip extension "quiz" or "assign" files
        self.skip_assignments: bool = True
        self.debugging = False

    def run(self):
        welcome()
        self.session = self.get_session()
        # OK but TODO: get_courses_all to go the ALL courses page to scrap everything!
        self.courses = self.get_courses()
        self.get_files()
        # BUG Some courses have clickable link sections (e.g. Responsible Leadership); therefore, we need to get the sections first ; make a recursive click to update the page source code ...
        # --> so TODO: deal with that recursively! modify the get_courses to recursively check the section's links (if any; i.e. those with a href and a url containing "/courses/" but not the one currently checked (avoiding infinite loops))
        self.session.mount(
            "https://",
            HTTPAdapter(pool_connections=self.pool_size,
                        pool_maxsize=self.pool_size),
        )
        self.create_saving_directory()
        self.save_text()
        self.save_files()
        self.clean_up_threads()

    def get_webdriver(self):
        attempts_left: int = 5
        chrome_options = webdriver.ChromeOptions()
        caps = DesiredCapabilities().CHROME

        if self.debugging is False:
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_prefs = {"profile.default_content_settings": {"images": 2}}
            chrome_options.experimental_options["prefs"] = chrome_prefs
            caps["pageLoadStrategy"] = "eager"

        while attempts_left > 0:
            try:
                driver = webdriver.Chrome(
                    chrome_options=chrome_options, desired_capabilities=caps
                )
            except Exception as e:
                logger.info(
                    "Encountered error while creating Selenium driver: %s", e)
                attempts_left -= 1
                continue
            break
        else:
            raise RuntimeError(
                "Could not create Selenium driver after 5 tries")

        return driver

    def get_session(self) -> requests.Session:
        if not (self.username and self.password):
            raise ValueError(
                "Username and password must be specified in "
                "environment variables or passed as arguments on the "
                "command line "
            )

        driver = self.get_webdriver()
        assert self.moodle_url is not None and self.moodle_url.endswith(
            "/"), "Moodle URL must be specified and end with a /"

        if self.login_url:
            driver.get(self.login_url)
        else:
            driver.get(self.moodle_url)

        _current_url = driver.current_url
        assert "cas" in _current_url or "CAS" in _current_url, "Not on CAS page"

        # find the username field and enter username
        username_field = driver.find_element(by=By.ID, value="username")
        username_field.send_keys(self.username)

        # find the password field and enter password
        password_field = driver.find_element(by=By.ID, value="password")
        password_field.send_keys(self.password)

        button = driver.find_element(
            by=By.XPATH, value="//button[@name='submit']")
        # BUG: I tried adding an attribute called login_url to the config file to manually avoid searching through undesired pages via /login/index.php...
        # Best would be to handle this from baseurl only? (sounds hard because multiple buttons can be found on the page if we don't specify the login page)

        # Click the button
        button.click()

        # Find the MoodleSession cookie that starts with MoodleSession
        # TODO: find a better way to do assert login success
        cookie_list = driver.get_cookies()
        cookie = None
        for c in cookie_list:
            if c["name"].startswith("MoodleSession"):
                cookie = c
                break
        assert cookie is not None, "Could not find MoodleSession cookie"

        # This is a hack to get around the fact that the MoodleSession cookie
        # is not being set properly (TODO: delete this?)
        session_requests = requests.session()
        cookies = driver.get_cookies()
        for cookie in cookies:
            session_requests.cookies.set(cookie["name"], cookie["value"])

        # Now, redirect to the Moodle home page
        driver.get(self.moodle_url)
        # Assert that we don't get redirected to the login page ; otherwise, save the page source to a file for debug
        if driver.current_url == f"{self.moodle_url}login/index.php" or (self.login_url and driver.current_url == self.login_url):
            with open("login.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info(
                "Could not log in to Moodle. Please check your username and "
                "password"
            )
            driver.close()
            sys.exit(1)

        driver.close()

        return session_requests

    def get_courses(self) -> Dict[str, str]:
        courses_dict: Dict[str, str] = {}
        url: str = f"{self.moodle_url}"
        result = self.session.get(url, headers=dict(referer=url), verify=False)
        soup = BeautifulSoup(result.text, HTML_PARSER)
        with open("courses.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())
        course_sidebar = soup.select("#nav-drawer > nav > ul")

        for header in course_sidebar[0].find_all("li"):
            if header.a and "/course/" in header.a["href"]:
                course_name = header.find_all(
                    "span", class_="media-body")[0].text.strip()
                course_link = header.a["href"]
                courses_dict[course_name] = course_link
                logger.info("Course: %s", course_name)

        self._check_exclusions(courses_dict)

        if not courses_dict:
            logger.error("Could not find any courses, exiting...")
            sys.exit(0)
        else:
            logger.info("Found %s courses successfully", len(courses_dict))

        return courses_dict

    def _check_exclusions(self, courses_dict):
        if self.config.excluded_courses:
            for course in courses_dict.copy():
                for exclusion in self.config.excluded_courses:
                    if exclusion in course.lower():
                        logger.info("Excluding course: %s", exclusion)
                        courses_dict.pop(course)

    def get_files(self) -> None:
        num_of_files: int = 0
        files_per_course: Dict[str, Dict[str, str]] = {}
        text_per_course: Dict[str, List[str]] = {}
        logger.info("Going through each course Moodle page")
        for course, link in self.courses.items():
            logger.info("Course: %s, link: %s", course, link)
            course_page = self.session.get(
                link, headers=dict(referer=link), verify=False
            )
            soup = BeautifulSoup(course_page.text, HTML_PARSER)

            text_list: List[str] = []
            for text in soup.find_all("div", {"class": "no-overflow"}):
                for text_block in text.find_all("p"):
                    text_list.append(text_block.getText())

            sanitized_course = get_valid_name(course)

            if text_list:
                text_list = [text.replace("\xa0", " ") for text in text_list]
                text_list = list(dict.fromkeys(text_list))
                text_per_course[sanitized_course] = text_list

            files_dict: Dict[str, str] = self._get_files_dict(soup)
            num_of_files += len(files_dict)
            files_per_course[sanitized_course] = files_dict

        logger.debug("Size of pool: %s", num_of_files)
        self.files = files_per_course
        self.paragraphs = text_per_course
        self.pool_size = num_of_files

    def _get_files_dict(self, soup) -> Dict[str, str]:
        files_dict: Dict[str, str] = {}

        for activity in soup.find_all("div", {"class": "activityinstance"}):
            file_type = activity.find("img")["src"]
            extension = self._get_extension(file_type)
            if not extension:
                continue

            try:
                file_name = activity.find(
                    "span", {"class": "instancename"}).text
                file_name = file_name.replace(" File", "").strip() + extension
                file_link = activity.find("a").get("href")
            except Exception as e:
                logger.error("Could not get file name or link: %s", e)
                continue

            self._log_file(file_name, file_link)
            files_dict[file_name] = file_link

            if HTML_EXT in extension:
                nested_files_dict = self._get_nested_files(file_link)
                files_dict = {**files_dict, **nested_files_dict}

        for file_in_sub_folder in soup.find_all("span", {"class": "fp-filename-icon"}):
            file_link = file_in_sub_folder.find("a").get("href")
            file_name = file_in_sub_folder.find(
                "span", {"class": "fp-filename"}).text
            self._log_file(file_name, file_link)
            files_dict[file_name] = file_link

        return files_dict

    def _log_file(self, file_name, file_link) -> None:
        logger.info("File name: %s", file_name)
        logger.info("File link: %s", file_link)

    def _get_extension(self, file_type) -> str:
        extension = ""
        if "icon" not in file_type:
            if "pdf" in file_type:
                extension = ".pdf"
            elif "powerpoint" in file_type:
                extension = ".pptx"
            elif "archive" in file_type:
                extension = ".zip"
            elif "text" in file_type:
                extension = ".txt"
            elif "spreadsheet" in file_type:
                extension = ".xlsx"
            elif "document" in file_type:
                extension = ".docx"
        elif "quiz" in file_type or "assign" in file_type:
            extension = HTML_EXT
        return extension

    def _get_nested_files(self, link) -> Dict[str, str]:
        """
        Recursive step to unfold nested files
        """
        result = self.session.get(
            link, headers=dict(referer=link), verify=False)
        soup = BeautifulSoup(result.text, HTML_PARSER)
        files_dict = {}
        for nested_file in soup.find_all("div", {"class": "fileuploadsubmission"}):
            a_tag = nested_file.find("a", {"target": "_blank"})
            file_link = a_tag.get("href")
            file_name = a_tag.text
            self._log_file(file_name, file_link)
            files_dict[file_name] = file_link

        return files_dict

    def create_saving_directory(self) -> None:
        this_path: str = self.directory

        if not self.directory:
            logger.debug(
                "Saving directory not specified, using current working directory"
            )
            this_path = f"{os.getcwd()}/courses"
            logger.debug(this_path)

        course_paths: List[str] = []

        if not os.path.exists(this_path):
            try:
                pathlib.Path(this_path).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(str(e))
                logger.error("Creation of the directory %s failed", this_path)
                raise OSError
            else:
                logger.info(
                    "Successfully created the directory %s ", this_path)
        else:
            logger.info("%s exists and will be used to save files", this_path)

        for course in self.files:
            course_path = f"{this_path}/{course}"
            course_paths.append(course_path)
            if not os.path.exists(course_path):
                try:
                    pathlib.Path(course_path).mkdir(
                        parents=True, exist_ok=True)
                except OSError as e:
                    logger.error(str(e))
                    logger.error(
                        "Creation of the directory %s failed", course_path)
                    raise OSError
                else:
                    logger.info(
                        "Successfully created the directory %s", course_path)
            else:
                logger.info(
                    "%s exists and will be used to save files", course_path)

        self.save_path = this_path
        self.course_paths_list = course_paths

    def save_text(self) -> None:
        for course, paragraph in self.paragraphs.items():
            current_path: str = f"{self.save_path}/{course}/course-information.txt"
            if os.path.exists(current_path):
                os.remove(current_path)
            with open(current_path, "w+", encoding="utf-8") as write_file:
                paragraph_text: List[str] = [
                    f"{text}\r\n" for text in paragraph]
                write_file.writelines(paragraph_text)
            logger.info("Wrote info for %s successfully", course)

    def save_files(self) -> None:
        for course, links in self.files.items():
            current_path: str = f"{self.save_path}/{course}"
            for name, link in links.items():
                name = name.replace("/", "")
                filename, extension = os.path.splitext(name)
                sanitized_name = get_valid_name(filename)
                sanitized_name = f"{sanitized_name}{extension}"
                if path.exists(f"{current_path}/{sanitized_name}"):
                    logging.debug(
                        "Already exists, skipping download: %s", sanitized_name)
                else:
                    t = Thread(
                        target=self._parallel_save_files,
                        kwargs={
                            "current_path": current_path,
                            "name": sanitized_name,
                            "link": link,
                        },
                    )
                    self.threads_list.append(t)
                    t.start()
                    msg: str = f"New file:\n{course}\n{sanitized_name}"
                    logger.info(msg)

    def _parallel_save_files(self, current_path=None, name=None, link=None) -> None:
        params_are_valid: bool = current_path and name and link

        if params_are_valid:
            sleep_time = self._get_next_wait_time()
            logger.info("Waiting %s seconds before downloading: %s",
                        sleep_time, name)
            sleep(sleep_time)
            try:
                if HTML_EXT in name:
                    env = Environment(loader=FileSystemLoader("assets"))
                    template = env.get_template("link_template.html")
                    output = template.render(url_name=name, url=link)

                    with open(f"{current_path}/{name}", "w") as write_file:
                        write_file.write(output)
                else:
                    request = self.session.get(
                        link, headers=dict(referer=link), verify=False
                    )
                    with open(f"{current_path}/{name}", "wb") as write_file:
                        write_file.write(request.content)
            except Exception as e:
                logger.error("File with same name is open | %s", str(e))
                # FIXME: log the full error and the line where this happens, especially the course name, course link, to
                # self-verify it ; happens that some files are open and cannot be downloaded (link_template.html simultaneously opened)... maybe a try catch block?
        else:
            logger.error("Some parameters were missing for parallel downloads")

    def clean_up_threads(self) -> None:
        for thread in self.threads_list:
            logger.debug("Joining downloading threads: %s", thread.getName())
            thread.join()

    def _get_next_wait_time(self) -> int:
        """
        Scheduling downloads to avoid overloading the server (1 download every 2-5 seconds)
        """
        wait_time = self.wait_time
        self.wait_time += randint(2, 5)
        return wait_time


def get_valid_name(source_file_name):
    """
    Remove any characters that are invalid for Windows directory names (e.g. ?, *, \, etc.)
    """
    valid_characters = r'[^\w\s-]'
    sanitized_name = re.sub(valid_characters, '', source_file_name)

    # truncate the name to 255 characters, which is the maximum length for Windows directory names
    truncated_name = sanitized_name[:255]

    if truncated_name != sanitized_name:
        logger.warning(
            f'"{source_file_name}" has been renamed to "{truncated_name}" because it is invalid for Windows.')
    return truncated_name
