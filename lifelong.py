import requests
from bs4 import BeautifulSoup as bs4
from urllib.parse import urljoin
# from urllib.request import urlretrieve
from pprint import pprint
# from os import path, makedirs
import jfileutil
import progressbar
import json
import re
import os
import selenium_login

import pandas as pd
import nest

import traceback

# import loom
# import progressbar

import asyncio

from snip import crawlApi, std_redirected, easySlug

content_base = "content3"


# def makeExtension(req):
#     extensions = {
#         "image/jpeg": ".jpg",
#         "text/html": ".html"
#     }
#     content_type = req.headers.get("Content-Type")
#     match = extensions.get(content_type.split(";")[0])
#     if match is None:
#         print("Unknown content type", content_type)
#         return ""
#     return match


# def save(request, filename):
#     (fdirs, fname) = path.split(filename)
#     makedirs(fdirs, exist_ok=True)
#     filename += makeExtension(request)
#     with open(filename, 'wb') as fd:
#         for chunk in request.iter_content(chunk_size=128):
#             fd.write(chunk)


def fetch(url, prev=None, soup=True):
    # print(url)
    if prev:
        url = urljoin(prev, url)
    # pprint(myCookies)
    req = session.get(url, cookies=myCookies)
    if soup:
        soup = bs4(req.text, features="html.parser")
        return (req, soup)
    else:
        return req


myCookies = dict()
session = requests.Session()


def fixCookies():
    return selenium_login.login(
        "https://elearning.utdallas.edu/",
        lambda browser: (browser.current_url == "https://elearning.utdallas.edu/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1")
    ).get("cookies")


def cookiesAreBad():
    req = fetch("https://elearning.utdallas.edu/learn/api/public/v1/courses", soup=False)
    # print(req, req.status_code == 401)
    # return any(h.status_code == 301 for h in .history)
    return req.status_code == 401


def writeCSV(data, fp, columns):
    fp.write(",".join(map(str, columns)) + "\n")
    fp.writelines(",".join('"{}"'.format(j.get(f)) for f in columns) + "\n" for j in data)


def dumpUsers():
    global users
    import nest
    users = getApiResults("https://elearning.utdallas.edu/learn/api/public/v1/users?limit=100")
    writeCSV(
        [{k: v for k, v in nest.Nest(u).flatten()} for u in users],
        open("users.csv", "w"),
        [k for k, v in nest.Nest(users[0]).flatten()]
    )


def getApiResults(url):
    results = []
    while url:
        m = fetch(url, soup=False).json()
        if m.get("status") and m.get("status") >= 400:
            return []
        try:
            results += m['results']
        except KeyError:
            return m
        if not m.get('paging'):
            break
        url = "https://elearning.utdallas.edu" + m['paging'].get('nextPage')
    return results


def getMe(netid):
    return fetch("http://elearning.utdallas.edu/learn/api/public/v1/users?userName=" + netid, soup=False).json()['results'][0]


def downloadAttachment(attachment, course, contentsid, parent):
    filename = attachment.get("fileName")
    if not os.path.exists(parent + "/" + filename):
        print("A:", parent + "/" + filename)
        request = fetch("http://elearning.utdallas.edu/learn/api/public/v1/courses/" + course['id'] + "/contents/" + contentsid + "/attachments/" + attachment.get("id") + "/download", soup=False)
        with open(parent + "/" + filename, 'wb') as fd:
            for chunk in request.iter_content(chunk_size=128):
                fd.write(chunk)
    # else:
    #     print("File exists:", parent + "/" + filename)


async def iterateContent(course, contentsid, parent):

    # Metadata identification

    try:
        cdata = fetch("http://elearning.utdallas.edu/learn/api/public/v1/courses/" + course['id'] + "/contents/" + contentsid, soup=False).json()
    except (TypeError, KeyError):
        pprint(contentsid)
        raise

    if cdata.get("status") and cdata.get("status") >= 400:
        return

    # Loop detection
    uuid = (contentsid, cdata.get("title"))
    if uuid in history:
        print("LOOP!", contentsid, "in", parent)
        # pprint(cdata)
        return
    else:
        history.append(uuid)

    try:
        print("CONTENT:", cdata.get("title"), cdata["contentHandler"].get("id"))
        contentHandler = cdata["contentHandler"].get("id")
    except KeyError:
        pprint(cdata)
        return
    
    thisroot = parent + "/" + easySlug(cdata['title'], directory=True) + " - " + contentsid

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
        iterateContent(course, cdata["contentHandler"].get("targetId"), parent)
    
    else:
        with std_redirected("./" + easySlug(contentHandler) + ".txt"):
            crawlApi(cdata)
        json.dump(cdata, open(thisroot + ".json", "w"))

    # Attachment handling

    for attachment in getApiResults("http://elearning.utdallas.edu/learn/api/public/v1/courses/" + course['id'] + "/contents/" + contentsid + "/attachments"):
        # spool.enqueue(downloadAttachment, (attachment, course, contentsid, parent,))
        downloadAttachment(attachment, course, contentsid, parent)

    # Recursion

    if cdata.get("hasChildren") is True:
        children = getApiResults("http://elearning.utdallas.edu/learn/api/public/v1/courses/" + course['id'] + "/contents/" + contentsid + "/children")
        for child in children:
            rootdir = parent + "/" + easySlug(cdata['title'], directory=True)
            # print("make", rootdir)
            os.makedirs(rootdir, exist_ok=True)
            await iterateContent(course, child['id'], rootdir)
            # iterateContent(course, child['id'], rootdir)

    # print(contentsid, "end")


async def saveGrades(courseId, courseName):
    global myGrades
    global columnsFrame
    columns = getApiResults("http://elearning.utdallas.edu/learn/api/public/v2/courses/{}/gradebook/columns".format(courseId))
    # try:
    #     crawlApi(columns)
    # except:
    #     pass

    # rootdir = os.path.join(content_base, easySlug(courseName, directory=True), "gradebook")
    # os.makedirs(rootdir, exist_ok=True)

    # filename = os.path.join(rootdir, easySlug("columns.json", directory=False))
    # with open(filename, "w") as fp:
    #     json.dump(columns, fp, indent=4)

    me = getMe("stg160130")
    myGrades = getApiResults("http://elearning.utdallas.edu/learn/api/public/v2/courses/{}/gradebook/users/{}".format(courseId, me['id']))
    # crawlApi(myGrades)

    # filename = os.path.join(rootdir, easySlug("results.json", directory=False))
    # with open(filename, "w") as fp:
    #     json.dump(myGrades, fp, indent=4)

    rootdir2 = os.path.join(content_base, "gradebook")
    os.makedirs(rootdir2, exist_ok=True)

    myGradesFrame = pd.DataFrame([{a: b for a, b in nest.Nest(k).flatten()} for k in myGrades])
    columnsFrame = pd.DataFrame([{a: b for a, b in nest.Nest(k).flatten()} for k in columns])

    mergedGradeData = pd.merge(myGradesFrame, columnsFrame, left_on='columnId', right_on='id')
    mergedGradeData.to_csv(os.path.join(rootdir2, easySlug(courseName) + ".csv"), sep=',')


async def saveAnnouncements(courseId, courseName):
    url = "https://elearning.utdallas.edu/webapps/blackboard/execute/announcement?method=search&course_id=" + courseId
    req, soup = fetch(url)
    announcements = soup.find("ul", id="announcementList").findAll("li")

    rootdir2 = os.path.join(content_base, easySlug(courseName, directory=True), "announcementList")
    os.makedirs(rootdir2, exist_ok=True)

    for a in announcements:
        try:
            try:
                title = re.sub("^\W*", "", a.find("h3").text)
            except AttributeError:
                title = re.sub("^\W*", "", next(a.children).text)
            print("ANNOUNCEMENT:", title)
            thisroot = rootdir2 + "/" + easySlug(title)
            with open(thisroot + " - " + hex(hash(a)) + ".html", "w", encoding="utf-8") as document:
                document.write(a.prettify())
        except Exception:
            print(a.prettify())
            traceback.print_exc()
            pass


async def iterateCourses():
    me = getMe("stg160130")
    myCourses = getApiResults("http://elearning.utdallas.edu/learn/api/public/v1/users/" + me['id'] + "/courses?sort=lastAccessed")
    for course in progressbar.progressbar(sorted(myCourses, key=lambda c: str(c.get("lastAccessed")))):
        # print(course['availability'])
        course = fetch("http://elearning.utdallas.edu/learn/api/public/v1/courses/" + course['courseId'], soup=False).json()
        # pprint(course)

        if course['availability'].get("available") == "No":
            continue
        if course['name'].find("F19") < 0:
            continue
        print("COURSE:", course['name'])

        try:
            await saveGrades(course['id'], course['name'])
        except KeyError:
            traceback.print_exc()
            
        try:
            await saveAnnouncements(course['id'], course['name'])
        except AttributeError:
            traceback.print_exc()

        # Save contents

        rootdir = os.path.join(content_base, easySlug(course['name'], directory=True))
        os.makedirs(rootdir, exist_ok=True)
        for contents in getApiResults("http://elearning.utdallas.edu/learn/api/public/v1/courses/" + course['id'] + "/contents"):
            await iterateContent(course, contents['id'], rootdir)



# global myCookies
myCookies = jfileutil.load("cookies", default=dict())

if cookiesAreBad():
    print("Please log in.")
    myCookies = fixCookies()
    assert not cookiesAreBad()
    jfileutil.save(myCookies, "cookies")
print("Login successful. ")



history = list()


async def main():

    await iterateCourses()


loop = asyncio.get_event_loop()
tasks = [  
    main(),
]
loop.run_until_complete(asyncio.wait(tasks))  

# loop.close()
