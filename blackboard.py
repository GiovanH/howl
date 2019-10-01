import requests
from bs4 import BeautifulSoup as bs4
from urllib.parse import urljoin
import os
import snip.filesystem
import snip.data
import traceback
import json
from pprint import pprint
import re
from snip.data import crawlApi

from snip.stream import std_redirected
from snip import jfileutil
import selenium_login

import tqdm

import snip.net
import snip.data
import snip.pwidgets
import snip.nest
import asyncio


class Cms():

    def __init__(self, urlbase, netid):
        super(Cms, self).__init__()
        self.urlbase = urlbase
        self.netid = netid
        self.loop = asyncio.get_event_loop()
        self.login()

    def login(self):
        self.session = requests.Session()

        self.cookies = jfileutil.load("cookies", default=dict())

        if self.cookiesAreBad():
            print("Please log in.")
            self.cookies = self.bakeCookies()
            assert not self.cookiesAreBad()
            jfileutil.save(self.cookies, "cookies")
        print("Login successful. ")

    def bakeCookies(self):
        return selenium_login.login(
            self.urlbase,
            lambda browser: (browser.current_url == urljoin(
                self.urlbase,
                "/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"
            ))
        ).get("cookies")

    def cookiesAreBad(self):
        req = self.fetch("/learn/api/public/v1/courses")
        # print(req, req.status_code == 401)
        # return any(h.status_code == 301 for h in .history)
        return req.status_code == 401

    def fetch(self, url, soup=False):
        target_url = urljoin(self.urlbase, url)
        # print(target_url)
        req = self.session.get(target_url, cookies=self.cookies)
        if soup:
            soup = bs4(req.text, features="html.parser")
            return (req, soup)
        else:
            return req

    def getApiResults(self, url):
        results = []
        while url:
            m = self.fetch(url, soup=False).json()
            if m.get("status") and m.get("status") >= 400:
                return []
            try:
                results += m['results']
            except KeyError:
                return m
            if not m.get('paging'):
                break
            url = self.urlbase + m['paging'].get('nextPage')
        return results

    def getUser(self, netid):
        return self.fetch("/learn/api/public/v1/users?userName=" + netid).json()['results'][0]

    def dumpAllUsers(self):
        import datetime
        users = self.getApiResults("/learn/api/public/v1/users?limit=100")
        snip.data.writeJsonToCsv(
            [{k: v for k, v in snip.nest.Nest(u).flatten()} for u in users],
            snip.filesystem.easySlug(f"allusers {str(datetime.datetime.now())}")
        )

    def allCourses(self):
        me = self.getUser(self.netid)
        __myCourses = self.getApiResults(f"/learn/api/public/v1/users/{me['id']}/courses?sort=lastAccessed")
        _myCourses = [Course(self, course['courseId']) for course in __myCourses]
        myCourses = [course for course in _myCourses if course.good]

        return myCourses

    def saveAllClasses(self):
        with tqdm.tqdm(self.allCourses(), unit="course") as progbar:
            for course in progbar:
                
                progbar.set_description(course.name)

                try:
                    self.loop.run_until_complete(course.saveUsers())
                except AttributeError:
                    traceback.print_exc()
                    
                try:
                    self.loop.run_until_complete(course.saveAnnouncements())
                except AttributeError:
                    traceback.print_exc()

                # Save contents
                    
                try:
                    self.loop.run_until_complete(course.saveContents())
                except AttributeError:
                    traceback.print_exc()

                # Save grades
                course.saveGrades()

            # return


class Course():

    def __init__(self, cms, courseId):
        super(Course, self).__init__()
        self.id = courseId
        self.cms = cms
        self.good = True
        self.name = "???"
        self.initialize()

    def fail(self):
        self.good = False

    def initialize(self):
        self.session = requests.Session()

        self.v1_courses = self.cms.fetch(f"/learn/api/public/v1/courses/{self.id}").json()
        if self.v1_courses['availability'].get("available") == "No":
            return self.fail()
        if self.v1_courses['name'].find("F19") < 0:
            return self.fail()

        self.name = self.v1_courses['name']

        self.rootdir = os.path.join("content", snip.filesystem.easySlug(self.name, directory=True))
        os.makedirs(self.rootdir, exist_ok=True)

    async def saveUsers(self):

        csvpath = os.path.join(self.rootdir, "users.csv")
        if os.path.isfile(csvpath):
            return
        else:
            print(csvpath)

        # Save user data
        v1_courses_users = self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/users")

        userids = [u.get("userId") for u in v1_courses_users]

        users = []
        for userId in tqdm.tqdm(userids, "Users", unit="users"):
            users.append(self.cms.getApiResults(f"/learn/api/public/v1/users/{userId}"))

        snip.data.writeJsonToCsv(users, csvpath, ext=False)

    def saveGrades(self):
        import pandas as pd
        me = self.cms.getUser(self.cms.netid)

        columns = self.cms.getApiResults(f"/learn/api/public/v2/courses/{self.id}/gradebook/columns")
        myGrades = self.cms.getApiResults(f"/learn/api/public/v2/courses/{self.id}/gradebook/users/{me['id']}")

        grades_rootdir = os.path.join(self.rootdir, "gradebook")
        os.makedirs(grades_rootdir, exist_ok=True)

        myGradesFrame = pd.DataFrame([{a: b for a, b in snip.nest.Nest(k).flatten()} for k in myGrades])
        columnsFrame = pd.DataFrame([{a: b for a, b in snip.nest.Nest(k).flatten()} for k in columns])

        mergedGradeData = pd.merge(myGradesFrame, columnsFrame, left_on='columnId', right_on='id')
        mergedGradeData.to_csv(os.path.join(grades_rootdir, snip.filesystem.easySlug(self.name) + ".csv"), sep=',')

    async def saveAnnouncements(self):

        # v1_courses_announcements = self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/announcements")
        
        # pprint(v1_courses_announcements)

        # announcements_root = os.path.join(self.rootdir, "announcementList")

        # for a in v1_courses_announcements:
        #     filename = f"{a.get('created')} - {snip.filesystem.easya(a.get('title'))}.html"
        #     with open(os.path.join(announcements_root, filename), "w", encoding="utf-8") as document:
        #         document.write(a.get('body'))

        url = "/webapps/blackboard/execute/announcement?method=search&course_id=" + self.id
        req, soup = self.cms.fetch(url, soup=True)

        try:
            announcements = soup.find("ul", id="announcementList").findAll("li")
        except AttributeError:
            # print("No announcements.")
            return

        announcement_dir = os.path.join(self.rootdir, "announcementList")
        os.makedirs(announcement_dir, exist_ok=True)

        for a in announcements:
            try:
                try:
                    title = re.sub("^\W*", "", a.find("h3").text)
                except AttributeError:
                    title = re.sub("^\W*", "", next(a.children).text)
                announcement_id = a.get("id")
                # print("ANNOUNCEMENT:", title)
                filepath = os.path.join(announcement_dir, f"{announcement_id} - {snip.filesystem.easySlug(title)}.html")
                with open(filepath, "w", encoding="utf-8") as document:
                    document.write(a.prettify())
            except Exception:
                print(a.prettify())
                traceback.print_exc()
                pass

    async def saveContents(self):
        self.history = []
        os.makedirs("./handlers/", exist_ok=True)
        with tqdm.tqdm(total=0, unit="file") as progbar:
            for contents in self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/contents"):
                await self._savecontents(contents['id'], self.rootdir, progbar)

    async def _savecontents(self, contentsId, _rootdir, progbar):
        progbar.total += 1
        progbar.update(0)
        # Metadata identification
        try:
            cdata = self.cms.fetch(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsId}").json()
        except (TypeError, KeyError):
            pprint(contentsId)
            raise

        if cdata.get("status") and cdata.get("status") >= 400:
            progbar.total -= 1
            progbar.update(0)
            return

        # Loop detection
        uuid = (contentsId, cdata.get("title"))
        if uuid in self.history:
            progbar.write(f"LOOP! {contentsId} in {_rootdir}")
            # pprint(cdata)
            progbar.total -= 1
            progbar.update(0)
            return
        else:
            self.history.append(uuid)

        try:
            # progbar.write(f"CONTENT: {cdata.get('title')} {cdata['contentHandler'].get('id')}")
            assert cdata["contentHandler"].get("id")
        except AssertionError:
            pprint(cdata)
            progbar.total -= 1
            progbar.update(0)
            return

        # Content handling

        await self.saveContentHandler(progbar, contentsId, cdata, _rootdir)

        # Recursion

        if cdata.get("hasChildren") is True:
            children = self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsId}/children")
            for child in children:                
                rootdir = os.path.join(_rootdir, snip.filesystem.easySlug(cdata['title'], directory=True) + " - " + contentsId)
                os.makedirs(rootdir, exist_ok=True)
                await self._savecontents(child['id'], rootdir, progbar)
                # iterateContent(course, child['id'], rootdir)

        progbar.update(1)
        # print(contentsid, "end")

    async def saveContentHandler(self, progbar, contentsId, cdata, _rootdir):

        contentHandler = cdata["contentHandler"].get("id")
        basepath = os.path.join(_rootdir, snip.filesystem.easySlug(cdata['title'], directory=True) + " - " + contentsId)

        htmltypes = [
            "resource/x-bb-document",
            "resource/x-bb-blankpage",
            "resource/x-bb-video",
            "resource/x-bb-assignment"
        ]

        singleFields = {
            "resource/x-bb-externallink": "url",
            "resource/x-bb-achievement": "title",
            # "resource/x-bb-asmt-test-link"
        }

        with std_redirected("./handlers/" + snip.filesystem.easySlug(contentHandler) + ".txt"):
            crawlApi(cdata)

        # Attachment handling

        for attachment in self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsId}/attachments"):
            # spool.enqueue(downloadAttachment, (attachment, course, contentsid, parent,))
            await self.downloadAttachment(attachment, contentsId, _rootdir)

        if contentHandler in [None, "resource/x-bb-file"]:
            pass

        elif contentHandler == "resource/x-bb-forumlink":
            forum_id = cdata["contentHandler"].get("discussionId")
            listview_url = f"https://elearning.utdallas.edu/webapps/discussionboard/do/forum?action=list_threads&course_id={self.id}&nav=discussion_board&conf_id=_266239_1&forum_id={forum_id}&forum_view=list"
            (req, listview_soup) = self.cms.fetch(listview_url, soup=True)
            table = listview_soup.find("table", id="listContainer_datatable")
            if not table:
                print("No table at url", listview_url)
                return
            for checkbox in table.findAll("input", type="checkbox", id=re.compile("[^(listContainer_selectAll)]")):
                thread_id = f"_{checkbox.get('value')}_1"
                tree_url = f"https://elearning.utdallas.edu/webapps/discussionboard/do/message?action=message_tree&course_id={self.id}&forum_id={forum_id}&message_id={thread_id}&nav=discussion_board&thread_id={thread_id}"
                (req, threadtree_soup) = self.cms.fetch(tree_url, soup=True)
                thread_name = False
                for message_div in threadtree_soup.findAll("div", id=re.compile("^_[0-9]+_[0-9]")):
                    message_id = message_div['id']
                    subject = message_div.find(id=re.compile("subject_")).text
                    author = message_div.find("span", class_="profileCardAvatarThumb").text.strip()
                    message_name = snip.filesystem.easySlug(f"[{author}] {subject}")
                    if not thread_name:
                        thread_name = message_name
                        os.makedirs(os.path.join(basepath, thread_name), exist_ok=True)
                    message_url = f"https://elearning.utdallas.edu/webapps/discussionboard/do/message?action=message_frame&course_id={self.id}&forum_id={forum_id}&nav=db_thread_list&nav=discussion_board&message_id={message_id}"
                    stream = self.cms.fetch(message_url)
                    snip.net.saveStreamAs(stream, os.path.join(basepath, thread_name, message_name + ".html"))

        elif contentHandler == "resource/x-bb-externallink":
            url = cdata["contentHandler"].get("url")
            with open(basepath + ".txt", "w", encoding="utf-8") as document:
                field = singleFields[contentHandler]
                document.write(cdata["contentHandler"].get(field))

            if re.match("https://docs.google.com/", url):
                # Google document

                gtypes = {
                    "document": ["pdf", "docx"],
                    "spreadsheets": ["xlsx"]
                }

                (gtype, docid,) = re.match("https://docs.google.com/([^/]+)/d/([^/]+)", url).groups()
                for format in gtypes.get(gtype, ["pdf"]):
                    dl_url = f"https://docs.google.com/{gtype}/export?format={format}&id={docid}"
                    snip.net.saveStreamAs(snip.net.getStream(dl_url), f"{basepath}.{format}")

            elif re.match("https://([A-Za-z0-9_-]+\.){0,1}box.com", url):
                # Box
                pass

            else:
                stream = snip.net.getStream(url)
                snip.net.saveStreamAs(stream, basepath + snip.net.guessExtension(stream))

        elif contentHandler == "resource/x-bb-folder":
            os.makedirs(os.path.join(basepath), exist_ok=True)
            json.dump(cdata, open(os.path.join(basepath, "folderinfo.json"), "w"), indent=4)

        elif contentHandler in htmltypes:
            with open(basepath + ".html", "w", encoding="utf-8") as document:
                document.write("<body>")
                document.write("<h2>{}</h2>\n".format(cdata.get('title')))
                document.write(cdata.get('body', "<No content.>"))
                document.write("\n</body>\n")
                document.write("<!-- {} -->".format(json.dumps(cdata, indent=4)))

        # Single-value items, like links and achievements.
        elif contentHandler in singleFields.keys():
            try:
                with open(basepath + ".txt", "w", encoding="utf-8") as document:
                    field = singleFields[contentHandler]
                    document.write(cdata["contentHandler"].get(field))
            except TypeError:
                print(field)
                pprint(cdata["contentHandler"])

        elif contentHandler == "resource/x-bb-courselink":
            self._savecontents(cdata["contentHandler"].get("targetId"), _rootdir, progbar)

        else:
            progbar.write(f"Unknown content type {contentHandler}")
            json.dump(cdata, open(basepath + ".json", "w"))

    async def downloadAttachment(self, attachment, contentsid, parent):
        filename = attachment.get("fileName")
        if not os.path.exists(os.path.join(parent, filename)):
            # print("A:", parent + "/" + filename)
            request = self.cms.fetch(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsid}/attachments/" + attachment.get("id") + "/download", soup=False)
            snip.net.saveStreamAs(request, os.path.join(parent, filename))
            # with open(parent + "/" + filename, 'wb') as fd:
            #     for chunk in request.iter_content(chunk_size=128):
            #         fd.write(chunk)
