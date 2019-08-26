import requests

import os


from snip import nest

from snip.filesystem import easySlug

import blackboard


# async def saveGrades(courseId, courseName):
#     global myGrades
#     global columnsFrame
#     columns = getApiResults("http://elearning.utdallas.edu/learn/api/public/v2/courses/{}/gradebook/columns".format(courseId))

#     me = getMe("stg160130")
#     myGrades = getApiResults("http://elearning.utdallas.edu/learn/api/public/v2/courses/{}/gradebook/users/{}".format(courseId, me['id']))

#     rootdir2 = os.path.join(content_base, "gradebook")
#     os.makedirs(rootdir2, exist_ok=True)

#     myGradesFrame = pd.DataFrame([{a: b for a, b in nest.Nest(k).flatten()} for k in myGrades])
#     columnsFrame = pd.DataFrame([{a: b for a, b in nest.Nest(k).flatten()} for k in columns])

#     mergedGradeData = pd.merge(myGradesFrame, columnsFrame, left_on='columnId', right_on='id')
#     mergedGradeData.to_csv(os.path.join(rootdir2, easySlug(courseName) + ".csv"), sep=',')


if __name__ == "__main__":
    cms = blackboard.Cms("https://elearning.utdallas.edu/", "stg160130")
    # cms.saveGrades()
    cms.saveAllClasses()


# loop.close()
