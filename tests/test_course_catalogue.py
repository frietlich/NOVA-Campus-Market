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

    def test_import_is_idempotent(self):
        before = len(db.all_catalogue_options())
        db.setup()
        self.assertEqual(before, len(db.all_catalogue_options()))


if __name__ == '__main__':
    unittest.main()
