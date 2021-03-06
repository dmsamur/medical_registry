from django.core.management.base import BaseCommand
from expert_report_pages.registry_checksums import RegistryCheckSumsPage
from expert_report_pages.sanctions_checksums import SanctionCheckSumsPage
from report_printer_clear.utils.report import Report, ReportParameters
from report_printer_clear.utils.wizard import AutomaticReportsWizard


class Command(BaseCommand):

    def handle(self, *args, **options):
        report = Report('summary_1.xls')
        report.add_page(RegistryCheckSumsPage())
        report.add_page(SanctionCheckSumsPage())

        report_wizard = AutomaticReportsWizard(report)
        report_wizard.create_reports(600)


