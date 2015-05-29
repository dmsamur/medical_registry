#! -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from report_printer_clear.management.commands.defects_report_pages.defects import DefectsPage
from report_printer_clear.utils.report import Report
from report_printer_clear.utils.wizard import AutomaticReportsWizard


class Command(BaseCommand):

    def handle(self, *args, **options):
        report = Report('defect.xls')
        report.add_page(DefectsPage())

        report_wizard = AutomaticReportsWizard(report, u'дефекты')
        report_wizard.create_reports(600)
