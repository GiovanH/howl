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
        req = self.session.get(target_url, cookies=self.cookies)
        # print(target_url)
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

    def saveGrades(self):
        raise NotImplementedError()

    def dumpAllUsers(self):
        users = self.cms.getApiResults("/learn/api/public/v1/users?limit=100")
        snip.data.writeJsonToCsv(
            [{k: v for k, v in snip.data.Nest(u).flatten()} for u in users],
            "allusers.csv"
        )

    def saveAllClasses(self):
        me = self.getUser(self.netid)
        myCourses = self.getApiResults(f"/learn/api/public/v1/users/{me['id']}/courses?sort=lastAccessed")
        for course in progressbar.progressbar(sorted(myCourses, key=lambda c: str(c.get("lastAccessed")))):
            course = Course(self, course['courseId'])

            if not course.good:
                continue

            print(course.name)

            print("Save users")
            try:
                self.loop.run_until_complete(course.saveUsers())
            except AttributeError:
                traceback.print_exc()
                
            print("Save announcements")
            try:
                self.loop.run_until_complete(course.saveAnnouncements())
            except AttributeError:
                traceback.print_exc()

            # Save contents
                
            print("Save contents")
            try:
                self.loop.run_until_complete(course.saveContents())
            except AttributeError:
                traceback.print_exc()

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

        # Save user data
        v1_courses_users = self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/users")

        userids = [u.get("userId") for u in v1_courses_users]
        users = [self.cms.getApiResults(f"/learn/api/public/v1/users/{userId}") for userId in userids]

        snip.data.writeJsonToCsv(users, os.path.join(self.rootdir, "users"))

    async def saveAnnouncements(self):
        url = "/webapps/blackboard/execute/announcement?method=search&course_id=" + self.id
        req, soup = self.cms.fetch(url, soup=True)

        try:
            announcements = soup.find("ul", id="announcementList").findAll("li")
        except AttributeError:
            print("No announcements.")
            return

        announcement_dir = os.path.join(self.rootdir, "announcementList")
        os.makedirs(announcement_dir, exist_ok=True)

        for a in announcements:
            try:
                try:
                    title = re.sub("^\W*", "", a.find("h3").text)
                except AttributeError:
                    title = re.sub("^\W*", "", next(a.children).text)
                print("ANNOUNCEMENT:", title)
                thisroot = announcement_dir + "/" + snip.filesystem.easySlug(title)
                with open(thisroot + " - " + hex(hash(a)) + ".html", "w", encoding="utf-8") as document:
                    document.write(a.prettify())
            except Exception:
                print(a.prettify())
                traceback.print_exc()
                pass

    async def saveContents(self):
        self.history = []
        for contents in self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/contents"):
            await self._savecontent(contents['id'], self.rootdir)

    async def _savecontent(self, contentsId, _rootdir):
        # Metadata identification
        try:
            cdata = self.cms.fetch(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsId}").json()
        except (TypeError, KeyError):
            pprint(contentsId)
            raise

        if cdata.get("status") and cdata.get("status") >= 400:
            return

        # Loop detection
        uuid = (contentsId, cdata.get("title"))
        if uuid in self.history:
            print("LOOP!", contentsId, "in", _rootdir)
            # pprint(cdata)
            return
        else:
            self.history.append(uuid)

        try:
            print("CONTENT:", cdata.get("title"), cdata["contentHandler"].get("id"))
            contentHandler = cdata["contentHandler"].get("id")
        except KeyError:
            pprint(cdata)
            return

        thisroot = _rootdir + "/" + snip.filesystem.easySlug(cdata['title'], directory=True) + " - " + contentsId

        # Content handling

        htmltypes = [
            "resource/x-bb-document",
            "resource/x-bb-blankpage",
            "resource/x-bb-video"
        ]

        singleFields = {
            "resource/x-bb-externallink": "url",
            "resource/x-bb-achievement": "title"
        }

        if contentHandler in [None, "resource/x-bb-file", "resource/x-bb-folder"]:
            pass
        elif contentHandler in htmltypes:
            with open(thisroot + ".html", "w", encoding="utf-8") as document:
                document.write("<body>")
                document.write("<h2>{}</h2>\n".format(cdata.get('title')))
                document.write(cdata.get('body', "<No content.>"))
                document.write("\n</body>\n")
                document.write("<!-- {} -->".format(json.dumps(cdata, indent=4)))

        # Single-value items, like links and achievements.
        elif contentHandler in singleFields.keys():
            try:
                with open(thisroot + ".txt", "w", encoding="utf-8") as document:
                    field = singleFields[contentHandler]
                    document.write(cdata["contentHandler"].get(field))
            except TypeError:
                print(field)
                pprint(cdata["contentHandler"])

        elif contentHandler == "resource/x-bb-courselink":
            self._savecontent(cdata["contentHandler"].get("targetId"), _rootdir)

        else:
            with std_redirected("./" + snip.filesystem.easySlug(contentHandler) + ".txt"):
                crawlApi(cdata)
            json.dump(cdata, open(thisroot + ".json", "w"))

        # Attachment handling

        for attachment in self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsId}/attachments"):
            # spool.enqueue(downloadAttachment, (attachment, course, contentsid, parent,))
            await self.downloadAttachment(attachment, contentsId, _rootdir)

        # Recursion

        if cdata.get("hasChildren") is True:
            children = self.cms.getApiResults(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsId}/children")
            for child in children:
                rootdir = _rootdir + "/" + snip.filesystem.easySlug(cdata['title'], directory=True)
                # print("make", rootdir)
                os.makedirs(rootdir, exist_ok=True)
                await self._savecontent(child['id'], rootdir)
                # iterateContent(course, child['id'], rootdir)

        # print(contentsid, "end")

    async def downloadAttachment(self, attachment, contentsid, parent):
        filename = attachment.get("fileName")
        if not os.path.exists(parent + "/" + filename):
            print("A:", parent + "/" + filename)
            request = self.cms.fetch(f"/learn/api/public/v1/courses/{self.id}/contents/{contentsid}/attachments/" + attachment.get("id") + "/download", soup=False)
            with open(parent + "/" + filename, 'wb') as fd:
                for chunk in request.iter_content(chunk_size=128):
                    fd.write(chunk)
