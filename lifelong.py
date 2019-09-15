import blackboard


if __name__ == "__main__":
    cms = blackboard.Cms("https://elearning.utdallas.edu/", "stg160130")
    # cms.saveGrades()
    cms.saveAllClasses()


# loop.close()
