#! -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from report_printer_clear.management.commands.defects_report_pages.defects import DefectsPage
from report_printer_clear.management.commands.summary_report_pages.sanctions_identify import SanctionsIdentifyPage

from summary_report_pages.order146 import Order146Page
from summary_report_pages.sanctions_reference import SanctionsReferencePage
from summary_report_pages.services_by_division import AcceptedServicesPage, InvoicedServicesPage
from summary_report_pages.services_by_sanctions import SanctionsPage
from summary_report_pages.sogaz_mek_detailed import SogazMekDetailedPage
from summary_report_pages.sogaz_mek_general import SogazMekGeneralPage
from report_printer_clear.utils.report import Report
from report_printer_clear.utils.wizard import AutomaticReportsWizard


class Command(BaseCommand):

    def handle(self, *args, **options):

        report_accepted = Report(template='reestr_201501.xls')

        if 'by_departments' in args:
            print u'Выгрузка по подразделениям'
            report_accepted.set_by_department()

        report_accepted.add_page(AcceptedServicesPage())
        report_accepted.add_page(SanctionsPage())
        report_accepted.add_page(SanctionsReferencePage())
        report_accepted.add_page(SanctionsIdentifyPage())
        report_accepted.add_page(Order146Page())
        report_accepted.add_page(SogazMekDetailedPage())
        report_accepted.add_page(SogazMekGeneralPage())

        report_invoiced = Report(template='reestr_201501.xls', suffix=u'поданные')
        report_invoiced.add_page(InvoicedServicesPage())

        report_defects = Report(template='defect.xls', suffix=u'дефекты')
        report_defects.add_page(DefectsPage())

        report_wizard_final = AutomaticReportsWizard(
            [report_accepted,
             report_invoiced, report_defects]
        )
        report_wizard_final.create_reports(8)

        report_wizard_preliminary = AutomaticReportsWizard([report_accepted])
        report_wizard_preliminary.create_reports(3)

        print u'Предварительные:'
        report_wizard_preliminary.print_completed_reports()

        print

        print u'После проверки экспертов:'
        report_wizard_final.print_completed_reports()
