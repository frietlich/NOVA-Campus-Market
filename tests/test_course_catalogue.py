"""Smoke tests for the official 2026/27 course catalogue."""
import os
import tempfile
import unittest

from app import db


class CourseCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, 'test.db')
        db.setup()

    def tearDown(self):
        db.DB_PATH = self.original_path
        self.temp.cleanup()

    def test_each_master_has_mandatory_courses(self):
        for programme in (
            'Master in Management', 'Master in Finance',
            'Master in Business Analytics', 'Master in Economics',
            'Master in Impact Entrepreneurship and Innovation',
            'Master in International Development and Public Policy',
        ):
            with self.subTest(programme=programme):
                self.assertTrue(any(c['course_type']=='MANDATORY'
                                    for c in db.courses_for_programme(programme)))

    def test_same_course_has_programme_specific_type(self):
        finance = {c['code']:c['course_type'] for c in db.courses_for_programme('Master in Finance')}
        management = {c['code']:c['course_type'] for c in db.courses_for_programme('Master in Management')}
        self.assertEqual(finance['2229'],'MANDATORY')
        self.assertEqual(management['2229'],'ELECTIVE')

    def test_courses_do_not_duplicate_by_term(self):
        management = db.courses_for_programme('Master in Management')
        self.assertEqual(sum(c['code']=='2477' for c in management), 1)

    def test_duplicate_official_code_is_displayed_without_collision(self):
        idpp = db.courses_for_programme('Master in International Development and Public Policy')
        records = [c for c in idpp if c['code']=='2743']
        self.assertEqual({c['name'] for c in records}, {'Policy Appraisal','Policy Analysis Exercise'})
        self.assertEqual(len({c['id'] for c in records}), 2)

    def test_bachelors_have_official_mandatory_courses(self):
        for programme in ('Bachelor in Management', 'Bachelor in Economics',
                          'Bachelor in Ocean Studies'):
            with self.subTest(programme=programme):
                courses = db.courses_for_programme(programme)
                self.assertTrue(any(c['course_type']=='MANDATORY' for c in courses))

    def test_bachelor_codes_are_distinct_from_master_codes(self):
        bachelor = {c['code']:c for c in db.courses_for_programme('Bachelor in Management')}
        master = {c['code']:c for c in db.courses_for_programme('Master in Management')}
        self.assertEqual(bachelor['1223']['name'], 'Strategy')
        self.assertEqual(master['2584']['name'], 'Strategy')

    def test_bachelor_type_is_programme_specific(self):
        econ = {c['code']:c['course_type'] for c in db.courses_for_programme('Bachelor in Economics')}
        mgmt = {c['code']:c['course_type'] for c in db.courses_for_programme('Bachelor in Management')}
        self.assertEqual(econ['1120'], 'MANDATORY')
        self.assertEqual(mgmt['1120'], 'ELECTIVE')
        self.assertEqual(mgmt['1490'], 'OUT_PROGRAM')

    def test_ocean_studies_pending_codes_are_independent(self):
        courses = db.courses_for_programme('Bachelor in Ocean Studies')
        unknown = [c for c in courses if c['code']=='XXXX']
        self.assertEqual(len(unknown), 5)
        self.assertEqual(len({c['id'] for c in unknown}), 5)
        self.assertEqual(len([c for c in courses if c['name']=='Principles of Oceanography']), 1)
        self.assertEqual(next(c['code'] for c in courses if c['name']=='Principles of Oceanography'),'1701')
        self.assertFalse(any(c['course_type']!='MANDATORY' for c in courses))

    def test_bachelor_career_modules_are_excluded(self):
        for programme in ('Bachelor in Management','Bachelor in Economics'):
            self.assertFalse(any('Careers with Impact' in c['name'] for c in db.courses_for_programme(programme)))

    def test_import_is_idempotent(self):
        before = len(db.all_catalogue_options())
        db.setup()
        self.assertEqual(before, len(db.all_catalogue_options()))


if __name__ == '__main__':
    unittest.main()
