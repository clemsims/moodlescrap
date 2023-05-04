# moodlescrap

```
      _____                    .___.__
     /     \   ____   ____   __| _/|  |   ____
    /  \ /  \ /  _ \ /  _ \ / __ | |  | _/ __ \
   /    Y    (  <_> |  <_> ) /_/ | |  |_\  ___/
   \____|__  /\____/ \____/\____ | |____/\___  >
           \/                   \/           \/
  _________
 /   _____/ ________________  ______   ___________
 \_____  \_/ ___\_  __ \__  \ \____ \_/ __ \_  __ \
 /        \  \___|  | \// __ \|  |_> >  ___/|  | \/
/_______  /\___  >__|  (____  /   __/ \___  >__|
        \/     \/           \/|__|        \/
```

MoodleScraper is a tool for scraping resources from Moodle.

## Description

This script downloads all resources for your specified moodle instance and saves it in a neat folder structure.

```
+--Courses/
|  +--Files.extension
|  +--course-information.txt
```

## Prerequisites (To be finished)

The script uses selenium, BeautifulSoup4, among other cool Python libs.

WARNING: You'll need to properly install selenium's webdriver for your browser of choice. This project uses webdriver for Chrome, but feel free to tweak the code to use your preferred browser. Please refer to the [selenium documentation](https://github.com/SergeyPirogov/webdriver_manager)
for more information.

```
pip install -r requirements.txt
```

## Configuration

- Modify scraper.json with the following information:

* username
* password
* directory to save the files (default: current directory of the package)
* your school Moodle url (warning: it must end with /)
* a login page url (optional, default: moodle url + login/index.php) in case your school uses a complex authentication system

- Also, you can exclude some courses by adding them to the exclude list in the excluded-courses.ini file
  Usage

---

```
python main.py
```

## Disclaimer

There is no warranty, expressed or implied, associated with this product.
Use at your own risk.
Product is not affiliated with Moodle Company or any of its affiliates in any way.

## Credits

My work was inspired by previous projects, often outdated. All credits go to the original authors.

- [Moodle](http://moodle.org)
- [moodle-scrapper](https://github.com/doebi/MoodleScraper)
- [moodlescrap](https://github.com/gordonpn/moodlescrap)
