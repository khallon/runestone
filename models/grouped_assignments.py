class Grade(object):
    """Grade of one user for either a collection of assignments, or for the whole course"""
    def __init__(self):
        self.total = 0
        self.possible = 0
        self.num_assignments = 0

    def percent(self, points=None):
        if points == None:
            points = self.total
        if self.possible == 0:
            return "0%"
        percent = round((points / self.possible) * 100)
        return "%d%%" % (percent)

    def projected(self):
        return self.percent()

def student_grade(user=None, course=None, assignment_type=None, predictive=False):
    grade = Grade()
    if not user or not course:
        return grade
    assignments = db(db.assignments.id == db.grades.assignment)
    assignments = assignments(db.assignments.course == course.id)
    assignments = assignments(db.grades.auth_user == user.id)
    if not predictive:
        assignments = assignments(db.assignments.released == True)
    if assignment_type:
        assignments = assignments(db.assignments.assignment_type == assignment_type.id)
    assignments = assignments.select(
        db.assignments.ALL,
        db.grades.ALL,
        orderby=db.assignments.name,
        )
    absolute_possible_points = 0
    remaining_points = 0
    # print assignments
    for row in assignments:
        if not predictive or (predictive and row.assignments.released):
            grade.total += row.grades.score
            grade.possible += row.assignments.points
            grade.num_assignments += 1
        if predictive and not row.assignments.released:
            remaining_points += row.assignments.points
        absolute_possible_points += row.assignments.points

    if predictive and grade.possible > 0:
        grade.absolute = absolute_possible_points
        grade.min = grade.total
        grade.max = grade.total + remaining_points
        grade.projected = grade.total + remaining_points * (grade.total / grade.possible)

    return grade

db.define_table('assignment_types',
    Field('name', 'string'),
    Field('grade_type', 'string', default="additive", requires=IS_IN_SET(['additive', 'checkmark', 'use'])),
    format='%(names)s',
    migrate='runestone_assignment_types.table',
    )

db.define_table('assignments',
    Field('course', db.courses),
    Field('assignment_type', db.assignment_types, requires=IS_EMPTY_OR(IS_IN_DB(db, 'assignment_types.id', '%(name)s'))),
    Field('name', 'string'),
    Field('points', 'integer'),
    Field('threshold', 'integer', default=1),
    Field('released', 'boolean'),
    format='%(name)s',
    migrate='runestone_assignments.table'
    )

class score(object):
    def __init__(self, acid=None, points=0, comment="", user=None):
        self.acid = acid
        self.user = user
        self.points = points
        self.comment = comment

def assignment_get_scores(assignment, problem=None, user=None, section_id=None):
    scores = []
    if problem and user:
        pass
    elif problem:
        grades = db(db.code.sid == db.auth_user.username)(db.code.acid == problem).select(
            db.code.ALL,
            db.auth_user.ALL,
            orderby=db.code.sid | db.code.timestamp,
            distinct=db.code.sid,
            )
        for g in grades:
            scores.append(score(
                points=g.code.grade,
                comment=g.code.comment,
                acid=problem,
                user=g.auth_user,
                ))
    elif user:
        q = db(db.problems.acid == db.code.acid)
        q = q(db.problems.assignment == assignment.id)
        q = q(db.code.sid == user.username)
        grades = q.select(
            db.code.acid,
            db.code.grade,
            db.code.comment,
            db.code.timestamp,
            orderby=db.code.acid | db.code.timestamp,
            distinct=db.code.acid,
            )
        for g in grades:
            scores.append(score(
                points=g.grade,
                comment=g.comment,
                acid=g.acid,
                user=user,
                ))
    else:
        grades = db(db.grades.assignment == assignment.id).select(db.grades.ALL)
        for g in grades:
            scores.append(score(
                points=g.score,
                user=g.auth_user,
                ))
    return scores
db.assignments.scores = Field.Method(lambda row, problem=None, user=None, section_id=None: assignment_get_scores(row.assignments, problem, user, section_id))

def assignment_set_grade(assignment, user):
    # delete the old grades; we're regrading
    db(db.grades.assignment == assignment.id)(db.grades.auth_user == user.id).delete()

    assignment_type = db(db.assignment_types.id == assignment.assignment_type).select().first()
    if not assignment_type:
        print "no assignment type"
        # if we don't know how to grade this assignment, don't grade the assignment.
        return 0

    points = 0.0
    if assignment_type.grade_type == 'use':
        for problem in db(db.problems.assignment == assignment.id).select():
            if db(db.useinfo.div_id == problem.acid)(db.useinfo.sid == user.username).select().first():
                points += 1
    else:
        for prob in assignment.scores(user=user):
            points = points + prob.points

    if assignment_type.grade_type in ['checkmark', 'use']:
        # threshold grade
        if points >= assignment.threshold:
            points = assignment.points
        else:
            points = 0
    else:
        # they got the points they earned
        pass

    db.grades.insert(
        auth_user=user.id,
        assignment=assignment.id,
        score=points,
        )
    return points
db.assignments.grade = Field.Method(lambda row, user: assignment_set_grade(row.assignments, user))

def assignment_release_grades(assignment, released=True):
    # update problems
    assignment.released = True
    assignment.update_record()
    return True
db.assignments.release_grades = Field.Method(lambda row, released=True: assignment_release_grades(row.assignments, released))

db.define_table('problems',
    Field('assignment', db.assignments),
    Field('acid', 'string'),
    migrate='runestones_problems.table',
    )

db.define_table('grades',
    Field('auth_user', db.auth_user),
    Field('assignment', db.assignments),
    Field('score', 'double'),
    migrate='runestone_grades.table',
    )

db.define_table('deadlines',
    Field('assignment', db.assignments, requires=IS_IN_DB(db, 'assignments.id', db.assignments._format)),
    Field('section', db.sections, requires=IS_EMPTY_OR(IS_IN_DB(db, 'sections.id', '%(name)s'))),
    Field('deadline', 'datetime'),
    migrate='runestone_deadlines.table',
    )
