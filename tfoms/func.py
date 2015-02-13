#! -*- coding: utf-8 -*-
from copy import deepcopy

from datetime import datetime
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from shutil import copy2
from dbfpy import dbf

from django.db.models import Q, Sum
from tfoms.models import (MedicalError, ProvidedService, MedicalRegister,
                          TariffFap, PaymentFailureCause,
                          MedicalRegisterRecord, Sanction,
                          MedicalOrganization, TariffCapitation,
                          MedicalWorkerSpeciality, MedicalServiceProfile,
                          MedicalService, MedicalDivision,
                          MedicalServiceSubgroup, MedicalServiceTerm,
                          TariffProfile, MedicalServiceGroup,
                          MedicalServiceReason, ProvidedServiceCoefficient,
                          TariffCoefficient,
                          ProvidedEventConcomitantDisease)

from medical_service_register.path import BASE_DIR, REESTR_PSE

from helpers.correct import date_correct

from pandas import DataFrame


### Значение даты следующей за отчётным периодом
def get_date_following_reporting_period(year, period):
    return datetime.strptime('{year}-{period}-1'.format(year=year,
                                                        period=period),
                             '%Y-%m-%d')
    #+ relativedelta(months=1)


def get_concomitant_disease(year, period, department):
    diseases = ProvidedEventConcomitantDisease.objects.filter(
        event__record__register__year=year,
        event__record__register__period=period,
        event__record__register__is_active=True,
        event__department__old_code=department
    ).values('event__id_pk', 'disease__idc_code')
    disease_list = {}
    for disease in diseases:
        if disease['event__id_pk'] not in disease_list:
            disease_list[disease['event__id_pk']] = disease['disease__idc_code']
    return disease_list


### Информация о пациентах в указанной больнице
def get_patients(year, period, mo_code):
    patients = MedicalRegisterRecord.objects.filter(
        register__year=year,
        register__period=period,
        register__is_active=True,
        register__organization_code=mo_code
    ).values(
        'patient__pk',                       # Ид пациента
        'patient__insurance_policy_series',  # Серия полиса
        'patient__insurance_policy_number',  # Номер полиса
        'patient__last_name',                # Фамилия пациета
        'patient__first_name',               # Имя пациента
        'patient__middle_name',              # Отчество пациента
        'patient__birthdate',                # Дата рождения
        'patient__gender__code',
        'id').distinct()

    patients_dict = {patient['patient__pk']
                     : {'policy_series': patient['patient__insurance_policy_series'],
                        'policy_number': patient['patient__insurance_policy_number'],
                        'last_name': patient['patient__last_name'],
                        'first_name': patient['patient__first_name'],
                        'middle_name': patient['patient__middle_name'],
                        'birthdate': patient['patient__birthdate'],
                        'gender_code': patient['patient__gender__code'],
                        'xml_id': patient['id']}

                     for patient in patients}
    return patients_dict


### Информация об услугах в указанной больнице
def get_services(year, period, mo_code, is_include_operation=False, department_code=None, payment_type=None,
                 payment_kind=None):
    services = ProvidedService.objects.filter(
        event__record__register__year=year,
        event__record__register__period=period,
        event__record__register__is_active=True,
        event__record__register__organization_code=mo_code
    )

    if department_code:
        services = services.filter(department__old_code=department_code)

    if payment_type:
        services = services.filter(payment_type_id__in=payment_type)

    if payment_kind:
        if payment_kind == [4, ]:
            services = services.filter(payment_kind_id__in=payment_kind)
        else:
            services = services.filter(Q(payment_kind_id__isnull=True) |
                                       Q(payment_kind_id__in=payment_kind))

    if not is_include_operation:
        services = services.exclude(code__group_id=27)

    services_values = services.values(
        'id_pk',                                            # Ид услуги
        'id',                                               # Ид из xml
        'event__anamnesis_number',                          # Амбулаторная карта
        'event__term__pk',                                  # Условие оказания МП
        'worker_code',                                      # Код мед. работника
        'quantity',                                         # Количество дней (услуг)
        'comment',                                          # Комментарий
        'code__pk',                                         # Ид кода услуги
        'code__code',                                       # Код услуги
        'code__name',                                       # Название услуги
        'start_date',                                       # Дата начала услуги
        'end_date',                                         # Дата конца услуги
        'basic_disease__idc_code',                          # Основной диагноз
        'event__concomitant_disease__idc_code',             # Сопутствующий диагноз
        'code__group__id_pk',                               # Группа
        'code__subgroup__id_pk',                            # Подгруппа услуги
        'code__reason__ID',                                 # Причина
        'division__code',                                   # Код отделения
        'division__term__pk',                               # Вид отделения
        'code__division__pk',                               # Ид отделения (для поликлиники)
        'code__tariff_profile__pk',                         # Тарифный профиль (для стационара и дн. стационара)
        'profile__pk',                                      # Профиль услуги
        'is_children_profile',                              # Возрастной профиль
        'worker_speciality__pk',                            # Специалист
        'payment_type__pk',                                 # Тип оплаты
        'payment_kind__pk',                                 # Вид оплаты
        'tariff',                                           # Основной тариф
        'invoiced_payment',                                 # Поданная сумма
        'accepted_payment',                                 # Принятая сумма
        'calculated_payment',                               # Рассчётная сумма
        'provided_tariff',                                  # Снятая сумма
        'code__uet',                                        # УЕТ
        'event__pk',                                        # Ид случая
        'department__old_code',                             # Код филиала
        'event__record__patient__pk'                        # Ид патиента
    ).order_by('event__record__patient__last_name',
               'event__record__patient__first_name',
               'event__pk', 'code__code')

    services_list = [
        {'id': service['id_pk'],
         'xml_id': service['id'],
         'anamnesis_number': service['event__anamnesis_number'],
         'term': service['event__term__pk'],
         'worker_code': service['worker_code'],
         'quantity': float(service['quantity'] or 1),
         'comment': service['comment'],
         'code_id': service['code__pk'],
         'code': service['code__code'],
         'name': service['code__name'],
         'start_date': service['start_date'],
         'end_date': service['end_date'],
         'basic_disease': service['basic_disease__idc_code'],
         'concomitant_disease': service['event__concomitant_disease__idc_code'],
         'group': service['code__group__id_pk'],
         'subgroup': service['code__subgroup__id_pk'],
         'reason': service['code__reason__ID'],
         'division_code': service['division__code'],
         'division_term': service['division__term__pk'],
         'division_id': service['code__division__pk'],
         'tariff_profile_id': service['code__tariff_profile__pk'],
         'profile': service['profile__pk'],
         'worker_speciality': service['worker_speciality__pk'],
         'payment_type': service['payment_type__pk'],
         'payment_kind': service['payment_kind__pk'],
         'tariff': service['tariff'],
         'invoiced_payment': service['invoiced_payment'],
         'accepted_payment': service['accepted_payment'],
         'calculated_payment': service['calculated_payment'] or 0,
         'provided_tariff': service['provided_tariff'] or service['tariff'],
         'uet': float(service['code__uet'] or 0) * float(service['quantity'] or 1),
         'event_id': service['event__pk'],
         'department': service['department__old_code'],
         'patient_id': service['event__record__patient__pk']}
        for service in services_values]

    return services_list


### Информация об ошибках в указанной больнице
def get_sanctions(year, period, mo_code):
    sanctions = Sanction.objects.filter(
        service__event__record__register__year=year,
        service__event__record__register__period=period,
        service__event__record__register__is_active=True,
        service__event__record__register__organization_code=mo_code,
        service__payment_type__in=[3, 4],
        type_id=1,
    )

    sanctions_list = sanctions.values(
        'id_pk',                                       # Ид санкции
        'error__pk',                                   # Ид ошибки
        'service__pk'                                  # Ид услуги
    ).order_by('-service__pk', '-error__weight').distinct()

    sanctions_dict = {}
    for sanction in sanctions_list:
        if sanction['service__pk'] not in sanctions_dict.keys():
            sanctions_dict[sanction['service__pk']] = []
        sanctions_dict[sanction['service__pk']].\
            append({'id': sanction['id_pk'], 'error': sanction['error__pk']})

    return sanctions_dict


def get_coefficients(year, period, mo_code):
    coefficients = ProvidedServiceCoefficient.objects.filter(
        service__event__record__register__year=year,
        service__event__record__register__period=period,
        service__event__record__register__is_active=True,
        service__event__record__register__organization_code=mo_code
    )

    coefficients_list = coefficients.values(
        'service__pk', 'coefficient__pk'
    ).distinct()
    coefficients_dict = {}
    for coefficient in coefficients_list:
        if coefficient['service__pk'] not in coefficients_dict:
            coefficients_dict[coefficient['service__pk']] = []
        coefficients_dict[coefficient['service__pk']].append(coefficient['coefficient__pk'])

    return coefficients_dict


### Ид случаев, по которым рассчитывается подушевое
def get_capitation_events(year, period, mo_code):
    data = get_date_following_reporting_period(year, period)
    mo_obj = MedicalOrganization.objects.get(code=mo_code, parent__isnull=True)
    return mo_obj.get_capitation_events(year, period, data)


### Ид случаев, по которым рассчитыватся обращения
def get_treatment_events(year, period, mo_code):
    events = ProvidedService.objects.filter(
        event__record__register__year=year,
        event__record__register__period=period,
        event__record__register__is_active=True,
        event__record__register__organization_code=mo_code).\
        filter(
            Q(code__subgroup__pk=12, code__group__pk=19) |
            (Q(code__reason__pk=1, event__term__pk=3) &
             (Q(code__group__isnull=True) | Q(code__group__pk=24)))
        )
    return events.values_list('event__pk', flat=True).distinct()


### Информация
def get_mo_info(mo_code, department_code=None):
    if department_code:
        mo = MedicalOrganization.objects.get(code=mo_code, old_code=department_code)
    else:
        mo = MedicalOrganization.objects.get(code=mo_code, parent__isnull=True)
    return {'name': mo.name, 'is_agma_cathedra': mo.is_agma_cathedra}


### Коды больниц прикреплённых к указанной больнице
def get_partial_register(year, period, mo_code):
    return ProvidedService.objects.filter(
        event__record__register__year=year,
        event__record__register__period=period,
        event__record__register__is_active=True,
        event__record__register__organization_code=mo_code).\
        values_list('department__old_code', flat=True).distinct()


### Справочники
### Справочник причин отказов
def get_failure_causes():
    return {failure_cause.pk: {'number': failure_cause.number,
                               'name': failure_cause.name}
            for failure_cause in PaymentFailureCause.objects.all()}


### Справочник ошибок
def get_errors():
    return {error.pk: {'code': error.old_code,
                       'failure_cause': error.failure_cause_id,
                       'name': error.name}
            for error in MedicalError.objects.all()}


### Справочник специальностей мед. работника
def get_medical_worker_speciality():
    return {worker.pk: {'code': worker.code,
                        'name': worker.name}
            for worker in MedicalWorkerSpeciality.objects.all()}


### Справочник медицинских профилей
def get_medical_profile():
    return {profile.pk: {'code': profile.code,
                         'name': profile.name}
            for profile in MedicalServiceProfile.objects.all()}


### Справочник тарифных профилей
def get_tariff_profile():
    return {profile.pk: {'name': profile.name}
            for profile in TariffProfile.objects.all()}


### Справочник медицинских услуг
def get_medical_code():
    return {service.pk: {'code': service.code,
                         'name': service.name}
            for service in MedicalService.objects.all()}


### Справочник медицинских отделений
def get_medical_division():
    return {division.pk: {'code': division.code,
                          'name': division.name}
            for division in MedicalDivision.objects.all()}


### Справочник медицинских групп
def get_medical_group():
    return {group.pk: {'name': group.name}
            for group in MedicalServiceGroup.objects.all()}


### Справочник медицинских подгрупп
def get_medical_subgroup():
    return {subgroup.pk: {'name': subgroup.name}
            for subgroup in MedicalServiceSubgroup.objects.all()}


### Справочник условий оказания мед. помощи
def get_medical_term():
    return {term.pk: {'name': term.name}
            for term in MedicalServiceTerm.objects.all()}


### Справочник причин оказания мед. помощи
def get_medical_reason():
    return {reason.pk: {'name': reason.name}
            for reason in MedicalServiceReason.objects.all()}


### Справочник типов коэффициентовы
def get_coefficient_type():
    return {coefficient.pk: {'name': coefficient.name, 'value': coefficient.value}
            for coefficient in TariffCoefficient.objects.all()}


### Итоговая сумма основного тарифа по МО
def get_total_sum(year, period, mo):
    total_sum = ProvidedService.objects.filter(
        event__record__register__year=year,
        event__record__register__period=period,
        event__record__register__is_active=True,
        organization__code=mo).aggregate(tariff=Sum('tariff'))
    return total_sum['tariff']


### Расчёт тарифа по подушевому по поликлинике и скорой помощи c января 2015
def calculate_capitation_tariff(term, year, period, mo_code):
    data_attachment = get_date_following_reporting_period(year, period)
    tariff = TariffCapitation.objects.filter(
        term=term, organization__code=mo_code,
        start_date__lte=data_attachment,
        is_children_profile=True
    )
    result = [
        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],
        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],

        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],
        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],

        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],
        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],

        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],
        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],

        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0],
        [0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0,  0, 0]
    ]

    if tariff:
        if term == 3:
            population = MedicalOrganization.objects.get(code=mo_code, parent__isnull=True).\
                get_attachment_count(data_attachment)
        elif term == 4:
            population = MedicalOrganization.objects.get(code=mo_code, parent__isnull=True).\
                get_ambulance_attachment_count(data_attachment)
    else:
        return False, result

    print '*', population
    # Чмсленность

    result[0][1] = population[1]['men']
    result[1][1] = population[1]['fem']

    result[2][1] = population[2]['men']
    result[3][1] = population[2]['fem']

    result[4][1] = population[3]['men']
    result[5][1] = population[3]['fem']

    result[6][0] = population[4]['men']
    result[7][0] = population[4]['fem']

    result[8][0] = population[5]['men']
    result[9][0] = population[5]['fem']

    # Тариф основной

    result[0][5] = tariff.filter(age_group=1, gender=1).order_by('-start_date')[0].value
    result[1][5] = tariff.filter(age_group=1, gender=2).order_by('-start_date')[0].value

    result[2][5] = tariff.filter(age_group=2, gender=1).order_by('-start_date')[0].value
    result[3][5] = tariff.filter(age_group=2, gender=2).order_by('-start_date')[0].value

    result[4][5] = tariff.filter(age_group=3, gender=1).order_by('-start_date')[0].value
    result[5][5] = tariff.filter(age_group=3, gender=2).order_by('-start_date')[0].value

    result[6][4] = tariff.filter(age_group=4, gender=1).order_by('-start_date')[0].value
    result[7][4] = tariff.filter(age_group=4, gender=2).order_by('-start_date')[0].value

    result[8][4] = tariff.filter(age_group=5, gender=1).order_by('-start_date')[0].value
    result[9][4] = tariff.filter(age_group=5, gender=2).order_by('-start_date')[0].value

    for idx in xrange(0, 10):
        result[idx][8] = result[idx][0]*result[idx][4]
        result[idx][9] = result[idx][1]*result[idx][5]

    if term == 3:
        fap = TariffFap.objects.filter(organization__code=mo_code,
                                       start_date__lte=data_attachment,
                                       is_children_profile=True)
        if fap:
            coeff = fap.order_by('-start_date')[0].value
            for idx in xrange(0, 10):
                result[idx][16] = result[idx][8]*(coeff-1)
                result[idx][17] = result[idx][9]*(coeff-1)

    for idx in xrange(0, 10):
        result[idx][22] = result[idx][8] + result[idx][16]
        result[idx][23] = result[idx][9] + result[idx][17]

    return True, result


'''
### Расчёт тарифа по подушевому по поликлинике и скорой помощи c сентября 2014
def calculate_capitation_tariff(term, year, period, mo_code):
    if term == 3:
        print u'Рассчёт подушевого по поликлиннике...'
    elif term == 4:
        print u'Рассчёт подушевого по скорой помощи...'
    data_attachment = get_date_following_reporting_period(year, period)
    tariff = TariffCapitation.objects.filter(term=term, organization__code=mo_code,
                                             start_date__lte=data_attachment)

    value_keys = (
        'adult',                     # Взрослые
        'children'                   # Дети
    )
    column_keys = (
        'population',                # Численность прикреплёных пациентов
        'tariff',                    # Тариф по подушевому
        'population_tariff',         # Численность * тариф по подушевому
        'coefficient_value',         # Величина коэффициента ФАП
        'coefficient',               # Коэффициент ФАП
        'accepted_payment'           # Численность * тариф + тариф * (1-ФАП)
    )

    init_sum = {column_key: {value_key: 0 for value_key in value_keys}
                for column_key in column_keys}
    capitation_data = {'male': deepcopy(init_sum), 'female': deepcopy(init_sum)}
    if tariff:
        if term == 4:
            population = MedicalOrganization.objects.get(code=mo_code, parent__isnull=True).\
                get_ambulance_attachment_count(data_attachment)
        elif term == 3:
            population = MedicalOrganization.objects.get(code=mo_code, parent__isnull=True).\
                get_attachment_count(data_attachment)

        # Численность прикреплённых
        capitation_data['male']['population']['adult'] = population['adults_male_count']
        capitation_data['male']['population']['children'] = population['children_male_count']
        capitation_data['female']['population']['adult'] = population['adults_female_count']
        capitation_data['female']['population']['children'] = population['children_female_count']

        """
        if term == 4:
            capitation_data['male']['population']['adult'] = 18533
            capitation_data['female']['population']['adult'] = 26517
        """

        # Подушевой тариф
        capitation_data['male']['tariff']['adult'] = tariff.filter(is_children_profile=False).\
            order_by('-start_date')[0].value\
            if population['adults_male_count'] else 0
        capitation_data['female']['tariff']['adult'] = capitation_data['male']['tariff']['adult']
        capitation_data['male']['tariff']['children'] = tariff.filter(is_children_profile=True).\
            order_by('-start_date')[0].value\
            if population['children_male_count'] else 0
        capitation_data['female']['tariff']['children'] = capitation_data['male']['tariff']['children']

        # Основой тариф
        capitation_data['male']['population_tariff']['adult'] = \
            capitation_data['male']['population']['adult'] * capitation_data['male']['tariff']['adult']
        capitation_data['male']['population_tariff']['children'] = \
            capitation_data['male']['population']['children'] * capitation_data['male']['tariff']['children']
        capitation_data['female']['population_tariff']['adult'] = \
            capitation_data['female']['population']['adult'] * capitation_data['female']['tariff']['adult']
        capitation_data['female']['population_tariff']['children'] = \
            capitation_data['female']['population']['children'] * capitation_data['female']['tariff']['children']

        # Для Магдагачи 280029
        """
        capitation_data['male']['population_tariff']['adult'] *= 2
        capitation_data['male']['population_tariff']['children'] *= 2
        capitation_data['female']['population_tariff']['adult'] *= 2
        capitation_data['female']['population_tariff']['children'] *= 2
        """

        # Коэффициент по подушевому
        if term == 3:
            fap = TariffFap.objects.filter(organization__code=mo_code,
                                           start_date__lte=data_attachment)
            if fap:
                capitation_data['male']['coefficient_value']['adult'] = \
                    fap.filter(is_children_profile=False).order_by('-start_date')[0].value
                capitation_data['female']['coefficient_value']['adult'] = \
                    capitation_data['male']['coefficient_value']['adult']
                capitation_data['male']['coefficient_value']['children'] = \
                    fap.filter(is_children_profile=True).order_by('-start_date')[0].value
                capitation_data['female']['coefficient_value']['children'] = \
                    capitation_data['male']['coefficient_value']['children']

                capitation_data['male']['coefficient']['adult'] = \
                    capitation_data['male']['population_tariff']['adult'] * \
                    (capitation_data['male']['coefficient_value']['adult']-1)
                capitation_data['female']['coefficient']['adult'] = \
                    capitation_data['female']['population_tariff']['adult'] * \
                    (capitation_data['female']['coefficient_value']['adult']-1)

                capitation_data['male']['coefficient']['children'] = \
                    capitation_data['male']['population_tariff']['children'] * \
                    (capitation_data['male']['coefficient_value']['children']-1)
                capitation_data['female']['coefficient']['children'] = \
                    capitation_data['female']['population_tariff']['children'] * \
                    (capitation_data['female']['coefficient_value']['children']-1)

        # Принятая к оплате
        capitation_data['male']['accepted_payment']['adult'] = \
            capitation_data['male']['population_tariff']['adult'] + Decimal(round(capitation_data['male']['coefficient']['adult'], 2))
        capitation_data['female']['accepted_payment']['adult'] = \
            capitation_data['female']['population_tariff']['adult'] + Decimal(round(capitation_data['female']['coefficient']['adult'], 2))

        capitation_data['male']['accepted_payment']['children'] = \
            capitation_data['male']['population_tariff']['children'] + \
            Decimal(round(capitation_data['male']['coefficient']['children'], 2))
        capitation_data['female']['accepted_payment']['children'] = \
            capitation_data['female']['population_tariff']['children'] + \
            Decimal(round(capitation_data['female']['coefficient']['children'], 2))

    return capitation_data
'''


### Коды больниц в медицинском реестре за указанный период
def get_mo_register(year, period, status=None):
    organizations = MedicalRegister.objects.filter(year=year, period=period, is_active=True, type=1)
    if status:
        organizations = organizations.filter(status__pk=status)
    return organizations.values_list('organization_code', flat=True)


### Экспорт реестра в PSE файла
### (P - файл пациентов, S - файл услуг, E - файл ошибок)
def pse_export(year, period, mo_code, register_status, data, handbooks):
    print u'Выгрузка в PSE файлы...'
    target_dir = REESTR_PSE
    templates_path = '%s/templates/dbf_pattern' % BASE_DIR
    errors_code = handbooks['errors_code']

    services = data['invoiced_services']
    patients = data['patients']
    sanctions = data['sanctions']

    # Группировка услуг по прикреплённым больницам
    services_group = {}
    for index, service in enumerate(services):
        if service['department'] not in services_group:
            services_group[service['department']] = []
        if service['group'] != 27:
            services_group[service['department']].append(index)

    for department in services_group:
        concomitant_diseases = get_concomitant_disease(year, period, department)
        rec_id = 1
        unique_patients = []
        copy2('%s/template_p.dbf' % templates_path,
              '%s/p%s.dbf' % (target_dir, department))
        copy2('%s/template_s.dbf' % templates_path,
              '%s/s%s.dbf' % (target_dir, department))
        copy2('%s/template_e.dbf' % templates_path,
              '%s/e%s.dbf' % (target_dir, department))
        p_file = dbf.Dbf('%s/p%s.dbf' % (target_dir, department))
        s_file = dbf.Dbf('%s/s%s.dbf' % (target_dir, department))
        e_file = dbf.Dbf('%s/e%s.dbf' % (target_dir, department))

        for index in services_group[department]:
            service = services[index]
            patient = patients[service['patient_id']]

            #Записываем данные услуги в S-файл
            s_rec = s_file.newRecord()
            s_rec['RECID'] = rec_id
            s_rec['MCOD'] = service['department']
            police = ' '.join([patient['policy_series'] or '99',
                               patient['policy_number'] or ''])
            s_rec['SN_POL'] = police.encode('cp866')
            s_rec['C_I'] = service['anamnesis_number'].encode('cp866')
            s_rec['OTD'] = service['division_code'] or ''
            s_rec['COD'] = float(service['code'])
            #s_rec['TIP'] = ''
            s_rec['D_BEG'] = date_correct(service['start_date'], service['id'], 'start_date')
            s_rec['D_U'] = date_correct(service['end_date'], service['id'], 'end_date')
            s_rec['K_U'] = service['quantity'] or 1
            s_rec['DS'] = (service['basic_disease'] or '').encode('cp866')
            s_rec['DS2'] = (concomitant_diseases.get(service['event_id'], '')).encode('cp866')
            #s_rec['TR'] = ''
            s_rec['EXTR'] = '0'
            s_rec['PS'] = 1 if service['term'] == 1 else 0
            s_rec['BE'] = '1'
            s_rec['TN1'] = service['worker_code'].encode('cp866')
            #s_rec['TN2'] = ''
            s_rec['TARIF'] = '1'
            s_rec['KLPU'] = '1'
            s_rec['KRR'] = 1
            s_rec['UKL'] = 1
            s_rec['SK'] = 1
            s_rec['S_ALL'] = service['tariff'] or 0
            s_rec['KSG'] = (service['comment'] or '').encode('cp866')
            s_rec['D_TYPE'] = '1'
            s_rec['STAND'] = 1000
            s_rec['K_U_O'] = 100
            s_rec['SRV_PK'] = service['id']
            s_rec.store()

            # Записываем пациентов в P-файл
            if service['patient_id'] not in unique_patients:
                p_rec = p_file.newRecord()
                p_rec['RECID'] = rec_id
                p_rec['MCOD'] = department
                p_rec['SN_POL'] = police.encode('cp866')
                p_rec['FAM'] = (patient['last_name'] or '').capitalize().encode('cp866')
                p_rec['IM'] = (patient['first_name'] or '').capitalize().encode('cp866')
                p_rec['OT'] = (patient['middle_name'] or '').capitalize().encode('cp866')
                p_rec['DR'] = date_correct(patient['birthdate'])
                p_rec['W'] = patient['gender_code']
                #p_rec['REGS'] = 0
                p_rec['NULN'] = ' '*20
                p_rec['UL'] = 0
                p_rec['DOM'] = ' '*7
                p_rec['KOR'] = ' '*5
                p_rec['STR'] = ' '*5
                p_rec['KV'] = ' '*5
                p_rec['ADRES'] = ' '*80
                p_rec['Q'] = 'DM'
                p_rec['KT'] = '  '
                #p_rec['SP'] = ''
                p_rec['VED'] = '  '
                #p_rec['MR'] = 0
                p_rec['D_TYPE'] = '1'
                p_rec.store()
                unique_patients.append(service['patient_id'])

            # Записываем ошибки в E-файл
            if sanctions.get(service['id']):
                unique_errors = []
                for sanction in sanctions[service['id']]:
                    if sanction['error'] not in unique_errors:
                        e_rec = e_file.newRecord()
                        e_rec['F'] = 'S'
                        e_rec['C_ERR'] = errors_code[sanction['error']]['code']
                        e_rec['N_REC'] = rec_id
                        e_rec['RECID'] = rec_id
                        e_rec['MCOD'] = department
                        e_rec.store()
                        unique_errors.append(sanction['error'])
            #Ставим на стоматологических приёмах ошибку HD
            if service['subgroup'] in [12, 13, 14, 17]:
                e_rec = e_file.newRecord()
                e_rec['F'] = 'S'
                e_rec['C_ERR'] = 'HD'
                e_rec['N_REC'] = rec_id
                e_rec['RECID'] = rec_id
                e_rec['MCOD'] = department
                e_rec.store()
            rec_id += 1
        p_file.close()
        s_file.close()
        e_file.close()
    change_register_status(year, period, mo_code, register_status)


### Устанавливает статус реестру
def change_register_status(year, period, mo_code, register_status):
    MedicalRegister.objects.filter(
        year=year,
        period=period,
        organization_code=mo_code,
        is_active=True
    ).update(status=register_status)
    '''
    register_files = MedicalRegister.objects.filter(year=year, period=period, organization_code=mo_code, is_active=True)
    for register_file in register_files:
        register_file.status_id = register_status
        register_file.save()
    '''