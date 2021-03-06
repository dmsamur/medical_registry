# -*- coding: utf-8 -*-

from funcs import safe_int, queryset_to_dict

from main.models import (
    IDC, MedicalOrganization,
    PersonIDType,
    MedicalServiceTerm, MedicalServiceKind, MedicalServiceForm, MedicalDivision,
    MedicalServiceProfile, TreatmentResult, TreatmentOutcome, Special,
    MedicalWorkerSpeciality, PaymentMethod, PaymentType, PaymentFailureCause,
    Gender, InsurancePolicyType, MedicalHospitalization, MedicalService,
    MedicalServiceHiTechKind, MedicalServiceHiTechMethod, ExaminationResult)


GENDERS = queryset_to_dict(Gender.objects.all())
POLICY_TYPES = queryset_to_dict(InsurancePolicyType.objects.all())
DEPARTMENTS = {rec.old_code: rec for rec in MedicalOrganization.objects.all()}
ORGANIZATIONS = queryset_to_dict(MedicalOrganization.objects.filter(parent=None))
TERMS = queryset_to_dict(MedicalServiceTerm.objects.all())
KINDS = queryset_to_dict(MedicalServiceKind.objects.all())
FORMS = queryset_to_dict(MedicalServiceForm.objects.all())
HOSPITALIZATIONS = queryset_to_dict(MedicalHospitalization.objects.all())
PROFILES = queryset_to_dict(MedicalServiceProfile.objects.filter(is_active=True))
OUTCOMES = queryset_to_dict(TreatmentOutcome.objects.all())
RESULTS = queryset_to_dict(TreatmentResult.objects.all())
SPECIALITIES_OLD = queryset_to_dict(MedicalWorkerSpeciality.objects.filter(
    is_active=False
))
SPECIALITIES_NEW = queryset_to_dict(MedicalWorkerSpeciality.objects.filter(
    is_active=True
))
METHODS = queryset_to_dict(PaymentMethod.objects.all())
TYPES = queryset_to_dict(PaymentType.objects.all())
FAILURE_CUASES = queryset_to_dict(PaymentFailureCause.objects.all())
DISEASES = {rec.idc_code: rec for rec in IDC.objects.all() if rec.idc_code or rec.idc_code != u'НЕТ'}
DIVISIONS = queryset_to_dict(MedicalDivision.objects.all())
SPECIALS = queryset_to_dict(Special.objects.all())
CODES = queryset_to_dict(MedicalService.objects.all())
PERSON_ID_TYPES = queryset_to_dict(PersonIDType.objects.all())
HITECH_KINDS = queryset_to_dict(MedicalServiceHiTechKind.objects.all())
HITECH_METHODS = queryset_to_dict(MedicalServiceHiTechMethod.objects.all())
EXAMINATION_RESULTS = queryset_to_dict(ExaminationResult.objects.all())

KIND_TERM_DICT = {'1': ['2', '3', '21', '22', '31', '32', '4'],
                  '2': ['1', '2', '3', '21', '22', '31', '32', '4'],
                  '3': ['1', '11', '12', '13', '4'],
                  '4': ['1', '2', '3', '4', '11', '12', '21', '22', '31', '32']
}

EXAMINATION_HEALTH_GROUP_EQUALITY = {
    '1': '1',
    '2': '2',
    '3': '3',
    '4':'4',
    '5':'5',
    '11': '1',
    '12': '2',
    '13': '3',
    '14': u'3а',
    '15': u'3б',
    '31': u'3а',
    '32': u'3б'}

ADULT_EXAMINATION_COMMENT_PATTERN = ur'^F(?P<student>[01])(?P<second_level>[01])(?P<veteran>[01])(?P<health_group>[123][абАБ]?)$'
ADULT_PREVENTIVE_COMMENT_PATTERN = r'^F(0|1)[0-3]{1}(0|1)$'

OLD_ADULT_EXAMINATION = ('019015', '019020', '019001', '019017', '19015', '19020', '19001', '19017')
NEW_ADULT_EXAMINATION = ('019025', '019026', '019027', '019028', '19025', '19026', '19027', '19028')
