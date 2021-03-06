#! -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Max, Q, F
from django.db import transaction
import time
from main.models import (
    ProvidedService, MedicalRegister, ProvidedServiceCoefficient,
    ExaminationAgeBracket, Sanction, SanctionStatus)

from helpers import mek_raw_query
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import re


def get_register_element():
    register_element = MedicalRegister.objects.filter(
        is_active=True, year='2015', status_id__in=(1, 5, 500),
    ) \
        .values('organization_code',
                'year',
                'period',
                'status') \
        .distinct().first()
    return register_element


STATUS_WORKING = 11
STATUS_MEK = 3
STATUS_AFTER_EXPERTS = 5
STATUS_FINISHED = 8


def set_status(register_element, status_code):
    MedicalRegister.objects.filter(
        is_active=True, year=register_element['year'],
        period=register_element['period'],
        organization_code=register_element['organization_code']) \
             .update(status=status_code)


def set_sanction(service, error_code):
    service.payment_type_id = 3
    service.accepted_payment = 0
    service.save()

    sanction = Sanction.objects.create(
        type_id=1, service=service, underpayment=service.invoiced_payment,
        error_id=error_code)

    SanctionStatus.objects.create(
        sanction=sanction,
        type=SanctionStatus.SANCTION_TYPE_ADDED_BY_MEK)


def set_sanctions(service_qs, error_code):
    with transaction.atomic():
        for service in service_qs:
            set_sanction(service, error_code)


def get_services(register_element):
    """
        Выборка всех услуг для МО
    """

    query = """
    select DISTINCT provided_service.id_pk,
        medical_service.code as service_code,
        (
            select min(ps2.start_date)
            from provided_service ps2
            where ps2.event_fk = provided_event.id_pk
        ) as event_start_date,
        case WHEN (
                select count(ps2.id_pk)
                   from provided_service ps2
                   join medical_service ms2 on ms2.id_pk = ps2.code_fk
                   where ps2.event_fk = provided_event.id_pk
                   and (ms2.group_fk != 27 or ms2.group_fk is null)) = 1
            and medical_service.reason_fk = 1
            and provided_event.term_fk=3
            and (medical_service.group_fk = 24 or medical_service.group_fk is NULL)
                THEN tariff_basic.capitation
            WHEN medical_service.group_fk = 19
                THEN COALESCE(medical_service.uet, 0)*tariff_basic.value
            ELSE
                tariff_basic.value  END as expected_tariff,
        provided_event.term_fk as service_term,
        medical_service.code as service_code,
        medical_service.examination_special as service_examination_special,
        medical_service.group_fk as service_group,
        medical_service.subgroup_fk as service_subgroup,
        medical_service.examination_group as service_examination_group,
        medical_service.tariff_profile_fk as service_tariff_profile,
        medical_service.reason_fk as reason_code,
        medical_service.vmp_group,
        provided_event.examination_result_fk as examination_result,
        COALESCE(case provided_event.term_fk
            when 1 THEN
                (
                    select tariff_nkd.value
                    from tariff_nkd
                    where start_date = (
                        select max(start_date)
                        from tariff_nkd
                        where start_date <= CASE
                                            when provided_service.end_date < '2015-01-01' then '2015-01-01'
                                            else provided_service.end_date end
                            and profile_fk = medical_service.tariff_profile_fk
                            and is_children_profile = provided_service.is_children_profile
                            and "level" = department.level
                    ) and profile_fk = medical_service.tariff_profile_fk
                        and is_children_profile = provided_service.is_children_profile
                        and "level" = department.level
                    order by start_date DESC
                    limit 1
                )
            WHEN 2 THEN
                (
                    select tariff_nkd.value
                    from tariff_nkd
                    where start_date = (
                        select max(start_date)
                        from tariff_nkd
                        where start_date <= CASE
                                            when provided_service.end_date < '2015-01-01' then '2015-01-01'
                                            else provided_service.end_date end
                            and profile_fk = medical_service.tariff_profile_fk
                            and is_children_profile = provided_service.is_children_profile
                    ) and profile_fk = medical_service.tariff_profile_fk
                        and is_children_profile = provided_service.is_children_profile
                    order by start_date DESC
                    limit 1
                )
            ELSE 1 END
        ) as nkd,
        case when medical_service.tariff_profile_fk IN (12) and medical_register.organization_code in ('280068', '280012', '280059')
        THEN (
                case when medical_organization.regional_coefficient = 1.6 then 34661
                when medical_organization.regional_coefficient = 1.7 then 36827
                WHEN medical_organization.regional_coefficient = 1.8 THEN 38994
                END
        ) else 0 end as alternate_tariff,
        medical_organization.is_agma_cathedra,
        medical_organization.level as level,
        patient.insurance_policy_fk as patient_policy,
        patient.birthdate as patient_birthdate,
        person.deathdate as person_deathdate,
        insurance_policy.stop_date as policy_stop_date,
        operation.reason_stop_fk as stop_reason,
        insurance_policy.type_fk as policy_type,
        medical_register.organization_code,
        provided_event.comment as event_comment,
        medical_register_record.is_corrected as record_is_corrected,
        CASE medical_service.group_fk
        when 19 THEN
            (
                select 1
                from provided_service inner_ps
                    join medical_service inner_ms
                        on inner_ps.code_fk = inner_ms.id_pk
                where inner_ps.event_fk = provided_event.id_pk
                    and inner_ms.group_fk = 19 and inner_ms.subgroup_fk = 17
                    and inner_ps.end_date = provided_service.end_date
            )
        ELSE
            NULL
        END as coefficient_4
    from
        provided_service
        join provided_event
            on provided_event.id_pk = provided_service.event_fk
        join medical_register_record
            on medical_register_record.id_pk = provided_event.record_fk
        join patient
            on patient.id_pk = medical_register_record.patient_fk
        left join insurance_policy
            on patient.insurance_policy_fk = insurance_policy.version_id_pk
        left join person
            on person.version_id_pk = insurance_policy.person_fk
        left join operation
            on operation.insurance_policy_fk = insurance_policy.version_id_pk
                and operation.id_pk = (
                    select op.id_pk
                    from operation op
                        join operation_status os
                            on op.id_pk = os.operation_fk
                    where op.insurance_policy_fk = insurance_policy.version_id_pk
                        and os.timestamp = (
                            select min(timestamp)
                            from operation_status
                            where operation_status.operation_fk = op.id_pk)
                    order by timestamp desc limit 1)
        join medical_register
            on medical_register_record.register_fk = medical_register.id_pk
        JOIN medical_service
            on medical_service.id_pk = provided_service.code_fk
        join medical_organization
            on medical_organization.code = medical_register.organization_code
                and medical_organization.parent_fk is null
        JOIN medical_organization department
            on department.id_pk = provided_service.department_fk
        LEFT join tariff_basic
            on tariff_basic.service_fk = provided_service.code_fk
                and tariff_basic.group_fk =
                    CASE
                    WHEN department.alternate_tariff_group_FK is NULL
                        THEN medical_organization.tariff_group_FK
                    ELSE department.alternate_tariff_group_FK
                    END
                and tariff_basic.start_date = '2015-01-01'
    where
        medical_register.is_active
        and medical_register.year = %(year)s
        and medical_register.period = %(period)s
        and medical_register.organization_code = %(organization_code)s
    """

    if register_element['status'] in (5, 500):
        query += ' and provided_service.payment_type_fk is NULL'

    services = list(ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization_code=register_element[
                        'organization_code'])))
    print 'total services: ', len(services)
    return services


def identify_patient(register_element):
    """
        Иденитификация пациентов по фио, полису, снилс, паспорту.
        В различных вариациях
    """
    query1 = """
        update patient set insurance_policy_fk = T.policy_id from (
        select DISTINCT p1.id_pk as patient_id, (
            select max(version_id_pk)
            from insurance_policy
            where id = (
                select insurance_policy.id
                from patient p2
                    JOIN insurance_policy
                        on version_id_pk = (
                            CASE
                            when char_length(p1.insurance_policy_number) <= 8 THEN
                                (select max(version_id_pk) from insurance_policy where id = (
                                    select id from insurance_policy where
                                        series = p2.insurance_policy_series
                                        and number = p2.insurance_policy_number
                                    order by stop_date DESC NULLS FIRST
                                    LIMIT 1
                                ))
                            when char_length(p1.insurance_policy_number) = 9 THEN
                                (select max(version_id_pk) from insurance_policy where id = (
                                    select id from insurance_policy where
                                        number = p2.insurance_policy_number
                                    order by stop_date DESC NULLS FIRST
                                    LIMIT 1
                                ))
                            when char_length(p1.insurance_policy_number) = 16 THEN
                                (select max(version_id_pk) from insurance_policy where id = (
                                    select insurance_policy.id from insurance_policy
                                        join person
                                            on insurance_policy.person_fk = person.version_id_pk
                                                and (
                                                    (person.last_name = p2.last_name
                                                        and person.first_name = p2.first_name
                                                        and person.middle_name = p2.middle_name
                                                        and person.birthdate = p2.birthdate)
                                                    or

                                                    ((
                                                        (person.first_name = p2.first_name
                                                        and person.middle_name = p2.middle_name)
                                                        or (person.last_name = p2.last_name
                                                        and person.first_name = p2.first_name
                                                        ) or (person.last_name = p2.last_name
                                                        and person.middle_name = p2.middle_name)
                                                    ) and person.birthdate = p2.birthdate)
                                                    or (
                                                        person.last_name = p2.last_name
                                                        and person.first_name = p2.first_name
                                                        and person.middle_name = p2.middle_name
                                                    ) or (
                                                        regexp_replace(regexp_replace((person.last_name || person.first_name || person.middle_name), 'Ё', 'Е' , 'g'), ' ', '' , 'g') = regexp_replace(regexp_replace((p2.last_name || p2.first_name || p2.middle_name), 'Ё', 'Е' , 'g'), ' ', '' , 'g')
                                                    )
                                                )

                                    where
                                        enp = p2.insurance_policy_number
                                    order by stop_date desc NULLS FIRST
                                    LIMIT 1
                                ))
                            else
                                NULL
                            end
                        )
                    join person
                        on insurance_policy.person_fk = person.version_id_pk
                            and (
                                (
                                    (
                                        p2.first_name = person.first_name
                                        or p2.middle_name = person.middle_name
                                        or p2.last_name = person.last_name
                                    ) and p2.birthdate = person.birthdate
                                ) or (
                                    p2.first_name = person.first_name
                                    and p2.middle_name = person.middle_name
                                ) or (p2.snils = person.snils)
                            )
                where p1.id_pk = p2.id_pk
                order by insurance_policy.version_id_pk DESC
                limit 1
            ) and is_active
        ) as policy_id
        from medical_register_record
        join medical_register mr1
            on medical_register_record.register_fk = mr1.id_pk
        JOIN patient p1
            on medical_register_record.patient_fk = p1.id_pk
        where mr1.is_active
            and mr1.year = %s
            and mr1.period = %s
            and mr1.organization_code = %s
            and p1.insurance_policy_fk is null) as T
        where id_pk = T.patient_id
    """

    query2 = """
        update patient set insurance_policy_fk = T.policy_id from (
        select DISTINCT p1.id_pk as patient_id,
            (
                select version_id_pk
                from insurance_policy
                where id = (
                    select insurance_policy.id
                    from patient p2
                        JOIN insurance_policy
                            on version_id_pk = (
                                CASE
                                when char_length(p1.insurance_policy_number) <= 8 THEN
                                    (select max(version_id_pk) from insurance_policy where id = (
                                        select id from insurance_policy where
                                            series = p2.insurance_policy_series
                                            and number = p2.insurance_policy_number
                                        order by stop_date DESC NULLS FIRST
                                        LIMIT 1
                                    ))
                                when char_length(p1.insurance_policy_number) = 9 THEN
                                    (select max(version_id_pk) from insurance_policy where id = (
                                        select id from insurance_policy where
                                            number = p2.insurance_policy_number
                                        order by stop_date DESC NULLS FIRST
                                        LIMIT 1
                                    ))
                                when char_length(p1.insurance_policy_number) = 16 THEN
                                    (select max(version_id_pk) from insurance_policy where id = (
                                        select id from insurance_policy where
                                            enp = p2.insurance_policy_number
                                        order by stop_date DESC NULLS FIRST
                                        LIMIT 1
                                    ))
                                else
                                    NULL
                                end
                            )
                    where p1.id_pk = p2.id_pk
                    order by insurance_policy.version_id_pk DESC
                    limit 1
                ) and is_active
            ) as policy_id
        from medical_register_record
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            JOIN patient p1
                on medical_register_record.patient_fk = p1.id_pk
        where mr1.is_active
            and mr1.year = %s
            and mr1.period = %s
            and mr1.organization_code = %s
            and p1.insurance_policy_fk is null
            and p1.newborn_code != '0'
            ) as T
        where id_pk = T.patient_id
    """

    query3 = """
        update patient set insurance_policy_fk = T.policy_id from (
            select DISTINCT p2.id_pk as patient_id,
                insurance_policy.version_id_pk as policy_id
            from patient p2
                join person_id
                    on person_id.id = (
                        select id from (
                            select person_id.id, stop_date
                            from person_id
                                join person
                                    on person.version_id_pk = person_id.person_fk
                                join insurance_policy
                                    on insurance_policy.person_fk = person.version_id_pk
                            where translate(upper(regexp_replace(person_id.series, '[ -/\\_]', '', 'g')), 'IOT', '1ОТ') = translate(upper(regexp_replace(p2.person_id_series, '[ -/\\_]', '', 'g')), 'IOT', '1ОТ')
                                and translate(upper(regexp_replace(person_id.number, '[ -/\\_]', '', 'g')), 'IOT', '1ОТ') = translate(upper(regexp_replace(p2.person_id_number, '[ -/\\_]', '', 'g')), 'IOT', '1ОТ')
                            order by insurance_policy.stop_date desc nulls first
                            limit 1
                        ) as T
                    ) and person_id.is_active

                JOIN person
                    ON person.version_id_pk = (
                        select max(version_id_pk)
                        from person
                        where id = (
                            select id from (
                            select DISTINCT person.id, stop_date
                            from person
                                join insurance_policy
                                    on person.version_id_pk = insurance_policy.person_fk
                            where replace(last_name, 'Ё', 'Е') = replace(p2.last_name, 'Ё', 'Е')
                                and replace(first_name, 'Ё', 'Е') = replace(p2.first_name, 'Ё', 'Е')
                                and replace(middle_name, 'Ё', 'Е') = replace(p2.middle_name, 'Ё', 'Е')
                                and birthdate = p2.birthdate
                            ORDER BY stop_date DESC NULLS FIRST
                            limit 1) as T
                        )
                    )
                join insurance_policy
                    on person.version_id_pk = insurance_policy.person_fk
                        and insurance_policy.is_active
                JOIN medical_register_record
                    on medical_register_record.patient_fk = p2.id_pk
                JOIN medical_register
                    ON medical_register.id_pk = medical_register_record.register_fk
            where medical_register.is_active
                and medical_register.year = %s
                and medical_register.period = %s
                and medical_register.organization_code = %s
                and p2.insurance_policy_fk is null
        ) as T where id_pk = T.patient_id
    """

    query4 = """
        update patient set insurance_policy_fk = T.policy_id from (
        select DISTINCT p2.id_pk as patient_id,
            insurance_policy.version_id_pk as policy_id
        from patient p2
            JOIN person
                ON person.version_id_pk = (
                    select max(version_id_pk)
                    from person
                    where id = (
                        select id from (
                        select DISTINCT person.id, stop_date
                        from person
                            join insurance_policy
                                on person.version_id_pk = insurance_policy.person_fk
                        where replace(first_name, 'Ё', 'Е') = replace(p2.first_name, 'Ё', 'Е')
                            and replace(middle_name, 'Ё', 'Е') = replace(p2.middle_name, 'Ё', 'Е')
                            and birthdate = p2.birthdate
                            and regexp_replace(person.snils, '[ -/\\_]', '', 'g') = regexp_replace(p2.snils, '[ -/\\_]', '', 'g')
                        ORDER BY stop_date DESC NULLS FIRST
                        limit 1) as T
                    )
                )
            join insurance_policy
                on person.version_id_pk = insurance_policy.person_fk
                    and insurance_policy.is_active
            JOIN medical_register_record
                on medical_register_record.patient_fk = p2.id_pk
            JOIN medical_register
                ON medical_register.id_pk = medical_register_record.register_fk
        where medical_register.is_active
            and medical_register.year = %s
            and medical_register.period = %s
            and medical_register.organization_code = %s
            and p2.insurance_policy_fk is null
        ) as T where id_pk = T.patient_id
    """
    cursor = connection.cursor()
    print u'идентификация по фио, снилс и полису'
    cursor.execute(query1, [register_element['year'],
                            register_element['period'],
                            register_element['organization_code']])
    transaction.commit()
    print u'идентификация новорожденных'
    cursor.execute(query2, [register_element['year'],
                            register_element['period'],
                            register_element['organization_code']])
    transaction.commit()
    print u'идентификация по паспорту'
    cursor.execute(query3, [register_element['year'],
                            register_element['period'],
                            register_element['organization_code']])
    transaction.commit()
    print u'идентификация по СИНЛС'
    cursor.execute(query4, [register_element['year'],
                            register_element['period'],
                            register_element['organization_code']])
    transaction.commit()
    cursor.close()


def update_patient_attacment_code(register_element):
    query = """
        update patient set attachment_code = T.code
        from (
        SELECT DISTINCT p.id_pk, att_org.code
        FROM medical_register_record mrr
            JOIN patient p
                on p.id_pk = mrr.patient_fk
            JOIN medical_register mr
                ON mrr.register_fk = mr.id_pk
            JOIN insurance_policy i
                ON p.insurance_policy_fk = i.version_id_pk
            JOIN person
                ON person.version_id_pk = (
                    SELECT version_id_pk
                    FROM person WHERE id = (
                        SELECT id FROM person
                        WHERE version_id_pk = i.person_fk) AND is_active)
            LEFT JOIN attachment
              ON attachment.id_pk = (
                  SELECT MAX(id_pk)
                  FROM attachment
                  WHERE person_fk = person.version_id_pk AND status_fk = 1
                     AND attachment.date <= (format('%%s-%%s-%%s', mr.year, mr.period, '01')::DATE) AND attachment.is_active)
            LEFT JOIN medical_organization att_org
              ON (att_org.id_pk = attachment.medical_organization_fk
                  AND att_org.parent_fk IS NULL)
                  OR att_org.id_pk = (
                     SELECT parent_fk FROM medical_organization
                     WHERE id_pk = attachment.medical_organization_fk
                  )
        WHERE mr.is_active
         AND mr.year = %(year)s
         AND mr.period = %(period)s
         and mr.organization_code = %(organization)s
         ) as T
        Where T.id_pk = patient.id_pk
    """

    cursor = connection.cursor()
    cursor.execute(query, dict(
        year=register_element['year'], period=register_element['period'],
        organization=register_element['organization_code']))

    transaction.commit()
    cursor.close()


def update_payment_kind(register_element):
    query = """
        update provided_service set payment_kind_fk = T.payment_kind_code
        from (
        select distinct ps1.id_pk service_pk, T1.pk, ps1.payment_type_fk,
            medical_service.code, ps1.end_date, T1.end_date, T1.period,
            case provided_event.term_fk
            when 3 then
                CASE
                    ((medical_service.group_fk = 24 and medical_service.reason_fk in (1, 2, 3, 8) and provided_event.term_fk=3)
                      or ((select count(ps2.id_pk)
                              from provided_service ps2
                              join medical_service ms2 on ms2.id_pk = ps2.code_fk
                              where ps2.event_fk = ps1.event_fk and
                              (ms2.group_fk != 27 or ms2.group_fk is null)) = 1
                           and medical_service.reason_fk = 1
                           and medical_service.group_fk is NULL and provided_event.term_fk=3)
                           and ps1.department_fk NOT IN (
                                90,
                                91,
                                92,
                                111,
                                115,
                                123,
                                124,
                                134)
                    )
                    AND ps1.department_fk NOT IN (15, 88, 89)
                when TRUE THEN
                    CASE p1.attachment_code = mr1.organization_code -- если пациент прикреплён щас к МО
                    when true THEN -- прикреплён
                        CASE
                        when T1.pk is not NULL
                            and T1.attachment_code = mr1.organization_code -- и был прикреплён тогда
                        THEN 2
                        when T1.pk is not NULL
                            and T1.attachment_code != mr1.organization_code -- и не был прикреплён тогда
                        THEN 3

                        ELSE 2
                        END
                    else -- не приреплён
                        CASE
                        when T1.pk is not NULL
                            and T1.attachment_code = mr1.organization_code
                        THEN 2
                        else 1
                        END
                    END
                ELSE
                    1
                END
            when 4 then 2
            else 1
            END as payment_kind_code
        from provided_service ps1
            join medical_service
                On ps1.code_fk = medical_service.id_pk
            join provided_event
                on ps1.event_fk = provided_event.id_pk
            join medical_register_record
                on provided_event.record_fk = medical_register_record.id_pk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            JOIN patient p1
                on medical_register_record.patient_fk = p1.id_pk
            join insurance_policy i1
                on i1.version_id_pk = p1.insurance_policy_fk
            LEFT JOIN (
                select ps.id_pk as pk, i.id as policy, ps.code_fk as code, ps.end_date,
                    ps.basic_disease_fk as disease, ps.worker_code, mr.year, mr.period,
                    p.attachment_code
                from provided_service ps
                    join provided_event pe
                        on ps.event_fk = pe.id_pk
                    join medical_register_record mrr
                        on pe.record_fk = mrr.id_pk
                    join medical_register mr
                        on mrr.register_fk = mr.id_pk
                    JOIN patient p
                        on mrr.patient_fk = p.id_pk
                    join insurance_policy i
                        on i.version_id_pk = p.insurance_policy_fk
                where mr.is_active
                    and mr.organization_code = %(organization)s
                    and format('%%s-%%s-%%s', mr.year, mr.period, '01')::DATE between format('%%s-%%s-%%s', %(year)s, %(period)s, '01')::DATE - interval '4 months' and format('%%s-%%s-%%s', %(year)s, %(period)s, '01')::DATE - interval '1 months'
                    and ps.payment_type_fk = 3
            ) as T1 on i1.id = T1.policy and ps1.code_fk = T1.code
                and ps1.end_date = T1.end_date and ps1.basic_disease_fk = T1.disease
                and ps1.worker_code = T1.worker_code
        where mr1.is_active
            and mr1.year = %(year)s
            and mr1.period = %(period)s
            and mr1.organization_code = %(organization)s

        ORDER BY payment_kind_code, T1.pk) as T
        where provided_service.id_pk = T.service_pk
    """

    cursor = connection.cursor()
    cursor.execute(query, dict(
        year=register_element['year'], period=register_element['period'],
        organization=register_element['organization_code']))

    transaction.commit()
    cursor.close()


def sanctions_on_repeated_service(register_element):
    """
        Санкции на повторно поданные услуги
    """
    query = """
        select distinct ps1.id_pk
        from provided_service ps1
            join medical_service
                On ps1.code_fk = medical_service.id_pk
            join provided_event
                on ps1.event_fk = provided_event.id_pk
            join medical_register_record
                on provided_event.record_fk = medical_register_record.id_pk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            JOIN patient p1
                on medical_register_record.patient_fk = p1.id_pk
            join insurance_policy i1
                on i1.version_id_pk = p1.insurance_policy_fk
            JOIN (
                select ps.id_pk as pk, i.id as policy, ps.code_fk as code, ps.end_date,
                    ps.basic_disease_fk as disease, ps.worker_code, mr.year, mr.period
                from provided_service ps
                    join provided_event pe
                        on ps.event_fk = pe.id_pk
                    join medical_register_record mrr
                        on pe.record_fk = mrr.id_pk
                    join medical_register mr
                        on mrr.register_fk = mr.id_pk
                    JOIN patient p
                        on mrr.patient_fk = p.id_pk
                    join insurance_policy i
                        on i.version_id_pk = p.insurance_policy_fk
                where mr.is_active
                    and mr.organization_code = %(organization)s
                    and format('%%s-%%s-%%s', mr.year, mr.period, '01')::DATE between  format('%%s-%%s-%%s', %(year)s, %(period)s, '01')::DATE - interval '5 months' and format('%%s-%%s-%%s', %(year)s, %(period)s, '01')::DATE  - interval '1 months'
                    and ps.payment_type_fk in (2, 4)
            ) as T1 on i1.id = T1.policy and ps1.code_fk = T1.code
                and ps1.end_date = T1.end_date and ps1.basic_disease_fk = T1.disease
                and ps1.worker_code = T1.worker_code
        where mr1.is_active
            and mr1.year = %(year)s
            and mr1.period = %(period)s
            and mr1.organization_code = %(organization)s
            and (
                select count(id_pk)
                from provided_service_sanction
                where service_fk = ps1.id_pk
                    and error_fk = 64
            ) = 0
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    return set_sanctions(services, 64)
    #return [(rec.pk, 1, rec.invoiced_payment, 64) for rec in services]


def sanctions_on_repeated_examination(register_element):
    """
        Санкции на повторно поданную диспансеризацию
        в рамках 2014 года
    """
    query1 = """
        select id_pk from provided_service where event_fk in (
            select distinct ps1.event_fk
            from provided_service ps1
                join medical_service
                    On ps1.code_fk = medical_service.id_pk
                join provided_event pe1
                    on ps1.event_fk = pe1.id_pk
                join medical_register_record
                    on pe1.record_fk = medical_register_record.id_pk
                join medical_register mr1
                    on medical_register_record.register_fk = mr1.id_pk
                JOIN patient p1
                    on medical_register_record.patient_fk = p1.id_pk
                join insurance_policy i1
                    on i1.version_id_pk = p1.insurance_policy_fk
            where mr1.is_active
                and mr1.year = %(year)s
                and mr1.period = %(period)s
                and mr1.organization_code = %(organization)s

                and medical_service.group_fk in (6, 7, 8, 10, 12, 13)
                and ps1.tariff > 0
                and EXISTS (
                    select 1
                    from provided_service ps2
                        join medical_service ms2
                            On ps2.code_fk = ms2.id_pk
                        join provided_event pe2
                            on ps2.event_fk = pe2.id_pk
                        join medical_register_record
                            on pe2.record_fk = medical_register_record.id_pk
                        join medical_register mr2
                            on medical_register_record.register_fk = mr2.id_pk
                        JOIN patient p2
                            on medical_register_record.patient_fk = p2.id_pk
                        join insurance_policy i2
                            on i2.version_id_pk = p2.insurance_policy_fk
                    WHERE mr2.is_active
                        and mr2.year = '2014'
                        and i1.id = i2.id
                        and pe1.id_pk <> pe2.id_pk
                        and ps1.id_pk <> ps2.id_pk
                        and NOT ((ps1.end_date = ps2.end_date) and (mr1.organization_code = mr1.organization_code))
                        and ms2.group_fk in (6, 7, 8, 10, 12, 13)
                        and ps2.payment_type_fk in (2, 4)
                        and ps2.accepted_payment > 0
                )
            )
        except
        select distinct ps1.id_pk
        from provided_service ps1
            join provided_event pe1
                on ps1.event_fk = pe1.id_pk
            join medical_register_record
                on pe1.record_fk = medical_register_record.id_pk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            JOIN provided_service_sanction pss
                on pss.service_fk = ps1.id_pk
        where mr1.is_active
            and mr1.year = %(year)s
            and mr1.period = %(period)s
            and mr1.organization_code = %(organization)s
            and pss.error_fk = 64
    """

    query2 = """
        select id_pk from provided_service where event_fk in (
            select distinct ps1.event_fk
            from provided_service ps1
                join medical_service
                    On ps1.code_fk = medical_service.id_pk
                join provided_event pe1
                    on ps1.event_fk = pe1.id_pk
                join medical_register_record
                    on pe1.record_fk = medical_register_record.id_pk
                join medical_register mr1
                    on medical_register_record.register_fk = mr1.id_pk
                JOIN patient p1
                    on medical_register_record.patient_fk = p1.id_pk
                join insurance_policy i1
                    on i1.version_id_pk = p1.insurance_policy_fk
            where mr1.is_active
                and mr1.year = %(year)s
                and mr1.period = %(period)s
                and mr1.organization_code = %(organization)s

                and medical_service.group_fk in (25, 26)
                and ps1.tariff > 0
                and EXISTS (
                    select 1
                    from provided_service ps2
                        join medical_service ms2
                            On ps2.code_fk = ms2.id_pk
                        join provided_event pe2
                            on ps2.event_fk = pe2.id_pk
                        join medical_register_record
                            on pe2.record_fk = medical_register_record.id_pk
                        join medical_register mr2
                            on medical_register_record.register_fk = mr2.id_pk
                        JOIN patient p2
                            on medical_register_record.patient_fk = p2.id_pk
                        join insurance_policy i2
                            on i2.version_id_pk = p2.insurance_policy_fk
                    WHERE mr2.is_active
                        and mr2.year = '2014'
                        and i1.id = i2.id
                        and pe1.id_pk <> pe2.id_pk
                        and ps1.id_pk <> ps2.id_pk
                        and NOT ((ps1.end_date = ps2.end_date) and (mr1.organization_code = mr1.organization_code))
                        and ms2.group_fk in (26, 25)
                        and ps2.payment_type_fk in (2, 4)
                        and ps2.accepted_payment > 0
                )
            )
        except
        select distinct ps1.id_pk
        from provided_service ps1
            join provided_event pe1
                on ps1.event_fk = pe1.id_pk
            join medical_register_record
                on pe1.record_fk = medical_register_record.id_pk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            JOIN provided_service_sanction pss
                on pss.service_fk = ps1.id_pk
        where mr1.is_active
            and mr1.year = %(year)s
            and mr1.period = %(period)s
            and mr1.organization_code = %(organization)s
            and pss.error_fk = 64
    """

    services1 = ProvidedService.objects.raw(
        query1, dict(year=register_element['year'],
                     period=register_element['period'],
                     organization=register_element['organization_code']))

    services2 = ProvidedService.objects.raw(
        query2, dict(year=register_element['year'],
                     period=register_element['period'],
                     organization=register_element['organization_code']))

    return (set_sanctions(services1, 64),
            set_sanctions(services2, 64))


def sanctions_on_ill_formed_adult_examination(register_element):
    """
        Санкции на взрослую диспансеризацю у которой в случае
        не хватает услуг (должна быть 1 платная и больше 0 бесплатных)
    """
    old_query = """
    select id_pk from provided_service where event_fk in (
        select distinct pe1.id_pk
        from provided_service ps1
            join medical_service
                On ps1.code_fk = medical_service.id_pk
            join provided_event pe1
                on ps1.event_fk = pe1.id_pk
            join medical_register_record
                on pe1.record_fk = medical_register_record.id_pk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps1.id_pk and pss.error_fk = 34
        where mr1.is_active
            and mr1.year = %s
            and mr1.period = %s
            and mr1.organization_code = %s
            and medical_service.group_fk in (7, 9)
            and NOT (
                (
                    select count(1)
                    from provided_service ps2
                        join medical_service ms2
                            on ms2.id_pk = ps2.code_fk
                    WHERE ps2.event_fk = pe1.id_pk
                        and ms2.examination_primary
                        and ps2.payment_type_fk = 2
                ) = 1 and EXISTS (
                    select 1
                    from provided_service ps2
                        join medical_service ms2
                            on ms2.id_pk = ps2.code_fk
                    WHERE ps2.event_fk = pe1.id_pk
                        and ms2.examination_specialist
                        and ps2.payment_type_fk = 2
                ) and (
                    select count(1)
                    from provided_service ps2
                        join medical_service ms2
                            on ms2.id_pk = ps2.code_fk
                    WHERE ps2.event_fk = pe1.id_pk
                        and ms2.examination_final
                        and ps2.payment_type_fk = 2
                ) = 1
            )
            and pss.id_pk is NULL
        ) and payment_type_fk != 3
    """
    query = """
        select ps.id_pk
        from
            (
                select distinct pe1.id_pk, (
                            select count(1)
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_primary
                                and ps2.payment_type_fk = 2
                        ) as primary_count,
                        (
                            select count(1)
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_specialist
                                and ps2.payment_type_fk = 2
                        ) as specialist_count,
                        (
                            select count(1)
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_final
                                and ps2.payment_type_fk = 2
                        ) as finals_count
                from -- provided_service ps1
                    --join medical_service
                    --    On ps1.code_fk = medical_service.id_pk
                    --join provided_event pe1
                    --    on ps1.event_fk = pe1.id_pk
                    provided_event pe1
                    join medical_register_record
                        on pe1.record_fk = medical_register_record.id_pk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                    --LEFT join provided_service_sanction pss
                    --   on pss.service_fk = ps1.id_pk and pss.error_fk = 34
                where mr1.is_active
                    and mr1.year = %s
                    and mr1.period = %s
                    and mr1.organization_code = %s
                    --and medical_service.group_fk in (7, 9)
                    --and pss.id_pk is NULL
            ) as T
            join provided_service ps
                on ps.event_fk = T.id_pk
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            LEFT join provided_service_sanction pss
               on pss.service_fk = ps.id_pk and pss.error_fk = 34

        where
            ms.group_fk in (7, 9)
            and (primary_count != 1 or specialist_count = 0 or finals_count != 1)
            and pss.id_pk is null
            and ps.payment_type_fk != 3
    """
    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 34)
    #return [(rec.pk, 1, rec.invoiced_payment, 34) for rec in services]


def sanctions_on_duplicate_services(register_element):
    """
        Санкции на дубликатные услуги
    """
    query = """
        select ps.id_pk
        FROM provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_register_record mrr
                on pe.record_fk = mrr.id_pk
            join medical_register mr
                on mrr.register_fk = mr.id_pk
            JOIN (
                select medical_register_record.patient_fk, ps1.code_fk,
                    ps1.basic_disease_fk, ps1.end_date, ps1.worker_code,
                    count(1)
                from provided_service ps1
                    join provided_event
                        on ps1.event_fk = provided_event.id_pk
                    join medical_register_record
                        on provided_event.record_fk = medical_register_record.id_pk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                where mr1.is_active
                    and mr1.year = %(year)s
                    and mr1.period = %(period)s
                    and mr1.organization_code = %(organization)s
                group by medical_register_record.patient_fk, ps1.code_fk,
                    ps1.basic_disease_fk, ps1.end_date, ps1.worker_code
                HAVING count(1) > 1
            ) as T on T.patient_fk = mrr.patient_fk and T.code_fk = ps.code_fk
                and ps.basic_disease_fk = T.basic_disease_fk and
                ps.end_date = T.end_date and ps.worker_code = T.worker_code
        where mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and (select id_pk from provided_service_sanction
                 where service_fk = ps.id_pk and error_fk = 67) is null
        EXCEPT
        select P.min from (
            select medical_register_record.patient_fk, ps1.code_fk,
                ps1.basic_disease_fk, ps1.end_date, ps1.worker_code,
                min(ps1.id_pk)
            from provided_service ps1
                join provided_event
                    on ps1.event_fk = provided_event.id_pk
                join medical_register_record
                    on provided_event.record_fk = medical_register_record.id_pk
                join medical_register mr1
                    on medical_register_record.register_fk = mr1.id_pk
            where mr1.is_active
                and mr1.year = %(year)s
                and mr1.period = %(period)s
                and mr1.organization_code = %(organization)s
            group by medical_register_record.patient_fk, ps1.code_fk,
                ps1.basic_disease_fk, ps1.end_date, ps1.worker_code
        ) as P

    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    return set_sanctions(services, 67)


def sanctions_on_cross_dates_services(register_element):
    """
        Санкции на пересечения дней в отделениях
        Поликлиника в стационаре
        И стационар в стационаре
    """
    query1 = """
        select ps.id_pk, T.id_pk
        FROM provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_service ms
                on ms.id_pk = ps.code_fk
            join medical_register_record mrr
                on pe.record_fk = mrr.id_pk
            join medical_register mr
                on mrr.register_fk = mr.id_pk
            JOIN (
                select medical_register_record.patient_fk, ps1.start_date, ps1.end_date, ps1.id_pk
                from provided_service ps1
                    JOIN medical_service ms
                        on ps1.code_fk = ms.id_pk
                    join provided_event
                        on ps1.event_fk = provided_event.id_pk
                    join medical_register_record
                        on provided_event.record_fk = medical_register_record.id_pk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                where mr1.is_active
                    and mr1.year = %(year)s
                    and mr1.year = %(year)s
                    and mr1.period = %(period)s
                    and mr1.organization_code = %(organization)s
                    and provided_event.term_fk = 1
                    and ms.group_fk not in (27, 5, 3)
            ) as T on T.patient_fk = mrr.patient_fk and (
                (ps.start_date > T.start_date and ps.start_date < T.end_date)
                or (ps.end_date > T.start_date and ps.end_date < T.end_date)
                and T.id_pk != ps.id_pk
            )
        where mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and pe.term_fk = 3
            and (ms.group_fk not in (27) and ms.group_fk is NULL)
            and (select count(1) from provided_service_sanction
                 where service_fk = ps.id_pk and error_fk = 73) = 0
        order by ps.id_pk
    """

    query2 = """
        select ps.id_pk, T.id_pk
        FROM provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_service ms
                on ms.id_pk = ps.code_fk
            join medical_register_record mrr
                on pe.record_fk = mrr.id_pk
            join medical_register mr
                on mrr.register_fk = mr.id_pk
            JOIN (
                select medical_register_record.patient_fk, ps1.start_date, ps1.end_date, ps1.id_pk
                from provided_service ps1
                    JOIN medical_service ms
                        on ps1.code_fk = ms.id_pk
                    join provided_event
                        on ps1.event_fk = provided_event.id_pk
                    join medical_register_record
                        on provided_event.record_fk = medical_register_record.id_pk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                where mr1.is_active
                    and mr1.year = %(year)s
                    and mr1.period = %(period)s
                    and mr1.organization_code = %(organization)s
                    and provided_event.term_fk in (1, 2)
                    and ms.group_fk not in (27, 5, 3)
            ) as T on T.patient_fk = mrr.patient_fk and (
                (ps.start_date > T.start_date and ps.start_date < T.end_date)
                or (ps.end_date > T.start_date and ps.end_date < T.end_date)
                and T.id_pk != ps.id_pk
            )
        where mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and pe.term_fk in (1, 2)
            and (ms.group_fk not in (27) and ms.group_fk is NULL)
            and (select count(1) from provided_service_sanction
                 where service_fk = ps.id_pk and error_fk = 73) = 0
        order by ps.id_pk
    """

    services1 = ProvidedService.objects.raw(
        query1, dict(year=register_element['year'],
                     period=register_element['period'],
                     organization=register_element['organization_code']))

    services2 = ProvidedService.objects.raw(
        query2, dict(year=register_element['year'],
                     period=register_element['period'],
                     organization=register_element['organization_code']))

    return set_sanctions(services1, 73) + set_sanctions(services2, 73)


def sanctions_on_disease_gender(register_element):
    """
        Санкции на несоответствие пола диагнозу
    """
    services = ProvidedService.objects.filter(
        ~Q(event__record__patient__gender=F('basic_disease__gender')),
        event__record__register__is_active=True,
        event__record__register__year=register_element['year'],
        event__record__register__period=register_element['period'],
        event__record__register__organization_code=register_element['organization_code']
    ).extra(where=['(select count(id_pk) from provided_service_sanction where service_fk = provided_service.id_pk and error_fk = 29) = 0'])

    return set_sanctions(services, 29)


def sanctions_on_service_gender(register_element):
    """
        Санкции на несоответствие пола услуге
    """
    services = ProvidedService.objects.filter(
        ~Q(event__record__patient__gender=F('code__gender')),
        event__record__register__is_active=True,
        event__record__register__year=register_element['year'],
        event__record__register__period=register_element['period'],
        event__record__register__organization_code=register_element['organization_code']
    ).extra(where=['(select count(id_pk) from provided_service_sanction where service_fk = provided_service.id_pk and error_fk = 41) = 0'])

    return set_sanctions(services, 41)


def sanctions_on_wrong_date_service(register_element):
    query = """
        select ps.id_pk--, i.id, ps.code_fk
        from provided_service ps
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join provided_event pe
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN patient p
                on p.id_pk = mrr.patient_fk
            JOIN insurance_policy i
                on i.version_id_pk = p.insurance_policy_fk
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and (
                ((ps.end_date < ((mr.year || '-' || mr.period || '-' || '01')::DATE - interval '2 month') and not mrr.is_corrected and not ms.examination_special)
                or (ps.end_date < ((mr.year || '-' || mr.period || '-' || '01')::DATE - interval '3 month') and mrr.is_corrected and not ms.examination_special)
                ) or (
                    ms.examination_special = True
                        and age((mr.year || '-' || mr.period || '-' || '01')::DATE - interval '1 month', ps.end_date) > '1 year'
                ) or (

                )
            ) and (select count(1) from provided_service_sanction where service_fk = ps.id_pk and error_fk = 32) = 0

    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 32)


def is_wrong_date(service, period):
    """
        Проврека на соответствие услуги периоду
    """
    current_period = period
    max_date = current_period + relativedelta(months=1)
    min_date = current_period - relativedelta(months=2)
    min_date_for_corrected = current_period - relativedelta(months=3)

    result = False

    if service.end_date > max_date:
        result = True

    if service.event_comment and service.event_comment.startswith('F1'):
        pass
    else:
        if service.end_date < min_date and not service.record_is_corrected:
            result = True

        if service.record_is_corrected and service.end_date < min_date_for_corrected:
            result = True

    return result


def sanctions_on_wrong_age_service(register_element):
    query = """
        select ps.id_pk
        from provided_service ps
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join provided_event pe
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN patient p
                on p.id_pk = mrr.patient_fk
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and NOT (ms.group_fk in (20, 7, 9, 10, 11, 12, 13, 14, 15, 16)
                or ms.code between '001441' and '001460' or
                 ms.code in ('098703', '098770', '098940', '098913', '098914', '019018'))
            and (
                (age(ps.end_date, p.birthdate) < '18 year' and substr(ms.code, 1, 1) = '0')
                or (age(ps.end_date, p.birthdate) >= '18 year' and substr(ms.code, 1, 1) = '1')
            ) and (select count(1) from provided_service_sanction where service_fk = ps.id_pk
                   and error_fk = 35) = 0
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 35)


def is_wrong_age(service):
    """
        Проверка на соответствие услуги возрасту
    """
    age = relativedelta(service.event_start_date,
                        service.patient_birthdate).years

    wrong_age = False

    EXCEPTION_CODES = ['00' + str(x) for x in range(1441, 1460)] + ['098703',
                                                                    '098770',
                                                                    '098940',
                                                                    '098913',
                                                                    '098914', ]
    code = service.service_code

    if code[0] == '0' and age < 18 and code not in EXCEPTION_CODES \
            and service.service_group not in (20, ):
        wrong_age = True
    elif code[0] == '1' and age >= 18:
        wrong_age = True

    return wrong_age


def sanctions_on_wrong_examination_age_group(register_element):
    query = """
        select ps.id_pk
        from provided_service ps
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join provided_event pe
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN patient p
                on p.id_pk = mrr.patient_fk
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and (date_part('year', ps.end_date) - date_part('year', p.birthdate)) >= 4
            and ((group_fk = 11
                and ps.tariff > 0
                and ms.examination_group != (
                    select "group"
                    from examination_age_bracket
                    where age = (date_part('year', ps.end_date) - date_part('year', p.birthdate))
                )) or (group_fk = 7
                and ms.examination_group != (
                    select "group"
                    from examination_age_bracket
                    where age = (date_part('year', ps.end_date) - date_part('year', p.birthdate))))
            )
            and (select count(1) from provided_service_sanction where service_fk = ps.id_pk
                           and error_fk = 35) = 0
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 35)


def is_wrong_examination_age_group(service):
    """
        Санкции на возрастную группу в диспансеризации
    """
    year = service.patient_birthdate.year

    if service.end_date < datetime.strptime('01-01-2014', "%d-%m-%Y").date():
        year += 1

    if service.service_code in ('019021', '019022', '019023', '019024'):
        try:
            group = ExaminationAgeBracket.objects.get(year=year).group
        except:
            group = None
        service_group = service.service_examination_group

        if group and service_group and int(group) != int(service_group):
            return True
    elif service.code.group_id == 11:
        provided_group = service.service_examination_group
        age = relativedelta(service.end_date,
                            service.patient_birthdate)
        if age.years >= 3:
            group = ExaminationAgeBracket.objects.filter(year=year, months=0)
            if group and group[0].group != provided_group:
                return True

        """
        else:
            months = age.years * 12 + age.months
            print age.months, months
            raw_group = ExaminationAgeBracket.objects.raw(
                "select id_pk \
                from examination_age_bracket \
                where months = (select max(months) \
                from examination_age_bracket \
                Where months <= %s )", [months])

            group = 0
            for rec in raw_group:
                group = rec.group

            if group != provided_group:
                return True
        """
    return False


def sanctions_on_not_paid_in_oms(register_element):
    """
        Санкции на диагнозы и услуги не оплачиваемые по ТП ОМС
    """
    services1 = ProvidedService.objects.filter(
        basic_disease__is_paid=False,
        event__record__register__is_active=True,
        event__record__register__year=register_element['year'],
        event__record__register__period=register_element['period'],
        event__record__register__organization_code=register_element['organization_code']
    ).extra(where=['(select id_pk from provided_service_sanction where service_fk = provided_service.id_pk and error_fk = 58) is null'])

    services2 = ProvidedService.objects.filter(
        code__is_paid=False,
        event__record__register__is_active=True,
        event__record__register__year=register_element['year'],
        event__record__register__period=register_element['period'],
        event__record__register__organization_code=register_element['organization_code']
    ).extra(where=['(select id_pk from provided_service_sanction where service_fk = provided_service.id_pk and error_fk = 58) is null'])

    return set_sanctions(services1, 58) + set_sanctions(services2, 59)


def drop_examination_event(register_element):
    """
        Санкции на случаи со снятыми услугами
    """
    query = """
        select provided_service.id_pk, 1, accepted_payment, T.error_id
        from provided_service
            join (
                select distinct pe1.id_pk as event_id, pss.error_fk as error_id
                from provided_service ps1
                    join medical_service ms
                        On ps1.code_fk = ms.id_pk
                    join provided_event pe1
                        on ps1.event_fk = pe1.id_pk
                    join medical_register_record
                        on pe1.record_fk = medical_register_record.id_pk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                    LEFT join provided_service_sanction pss
                        on pss.id_pk = (
                            select provided_service_sanction.id_pk
                            from provided_service_sanction
                                join medical_error
                                    on provided_service_sanction.error_fk = medical_error.id_pk
                            WHERE provided_service_sanction.service_fk = ps1.id_pk
                            ORDER BY weight, provided_service_sanction.id_pk DESC
                            LIMIT 1
                        )
                where mr1.is_active
                    and mr1.year = %s
                    and mr1.period = %s
                    and mr1.organization_code = %s
                    and ms.group_fk in (7, 9, 11, 12, 13, 15, 16)
                    and (ms.examination_primary or ms.examination_final)
                    and ps1.payment_type_fk = 3
                    and exists (
                        select 1
                        from provided_service
                        where event_fk = pe1.id_pk
                            and payment_type_fk = 2
                    )
                    and pss.error_fk is not null) as T
                ON T.event_id = provided_service.event_fk
            LEFT JOIN provided_service_sanction
                on provided_service_sanction.service_fk = provided_service.id_pk
                    and provided_service_sanction.error_fk = T.error_id
        WHERE provided_service_sanction.id_pk is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    errors = [(rec.pk, 1, rec.accepted_payment, rec.error_id) for rec in list(services)]
    errors_pk = [rec[0] for rec in errors]

    ProvidedService.objects.filter(pk__in=errors_pk).update(
        accepted_payment=0, payment_type=3)

    errors_objs = []
    for rec in errors:
        errors_objs.append(Sanction(service_id=rec[0], type_id=1,
                                    underpayment=rec[2], error_id=rec[3]))

    Sanction.objects.bulk_create(errors_objs)


def sanctions_on_invalid_stomatology_event(register_element):
    """
        Санкции на неверно оформленные случаи стоматологии
    """
    query = """
        select ps1.id_pk
        from provided_service ps1
            join medical_organization
                on ps1.department_fk = medical_organization.id_pk
            join medical_service
                On ps1.code_fk = medical_service.id_pk
            left join medical_service_subgroup
                on medical_service.subgroup_fk = medical_service_subgroup.id_pk
            join provided_event pe1
                on ps1.event_fk = pe1.id_pk
            join medical_register_record
                on pe1.record_fk = medical_register_record.id_pk
            join patient p1
                on p1.id_pk = medical_register_record.patient_fk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
        where mr1.is_active
            and mr1.year = %s
            and mr1.period = %s
            and mr1.organization_code = %s
            and (
                    (
                        medical_service.subgroup_fk is NULL
                        and medical_service.group_fk = 19
                        and not exists (
                            SELECT 1
                            from provided_service ps2
                            join medical_service
                                On ps2.code_fk = medical_service.id_pk
                            join provided_event pe2
                                on ps2.event_fk = pe2.id_pk
                            join medical_register_record
                                on pe2.record_fk = medical_register_record.id_pk
                            join medical_register mr2
                                on medical_register_record.register_fk = mr2.id_pk
                            where pe1.id_pk = pe2.id_pk
                                and ps1.end_date = ps2.end_date
                                and medical_service.subgroup_fk in (12, 13, 14, 17)
                                and ps2.payment_type_fk = 2
                            )
                    ) OR (
                        medical_service.subgroup_fk in (12, 13, 14, 17)
                        and not exists (
                            SELECT 1
                            from provided_service ps2
                            join medical_service
                                On ps2.code_fk = medical_service.id_pk
                            join provided_event pe2
                                on ps2.event_fk = pe2.id_pk
                            join medical_register_record
                                on pe2.record_fk = medical_register_record.id_pk
                            join medical_register mr2
                                on medical_register_record.register_fk = mr2.id_pk
                            where pe1.id_pk = pe2.id_pk
                                and ps1.end_date = ps2.end_date
                                and medical_service.subgroup_fk is NULL
                                and medical_service.group_fk = 19
                                and ps2.payment_type_fk = 2
                        )
                    )
            )
            and ps1.payment_type_fk <> 3
            and (select count(*) from provided_service_sanction
                 where service_fk = ps1.id_pk
                    and error_fk = 34) = 0
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 34)


def sanctions_on_invalid_outpatient_event(register_element):
    """
        Санкции на неверно оформленные услуги по поликлинике с заболеванием
    """
    query = """
        select id_pk from provided_service
        where event_fk in (
            select distinct provided_event.id_pk
            from
                provided_service
                join medical_organization department
                    on department.id_pk = provided_service.department_fk
                JOIN medical_service ms
                    on ms.id_pk = provided_service.code_fk
                join provided_event
                    on provided_event.id_pk = provided_service.event_fk
                join medical_register_record
                    on medical_register_record.id_pk = provided_event.record_fk
                join medical_register
                    on medical_register_record.register_fk = medical_register.id_pk
            where
                medical_register.is_active
                and medical_register.year = %s
                and medical_register.period = %s
                and medical_register.organization_code = %s
                --and department.level <> 3
                and ((
                        select count(1)
                        from provided_service
                            join medical_service
                                on provided_service.code_fk = medical_service.id_pk
                        where provided_service.event_fk = provided_event.id_pk
                            and provided_service.tariff > 0
                            and medical_service.reason_fk = 1 and (medical_service.group_fk != 19
                                or medical_service.group_fk is NUll)
                    ) > 1 or (
                        (
                            select count(1)
                            from provided_service
                                join medical_service
                                    on provided_service.code_fk = medical_service.id_pk
                            where provided_service.event_fk = provided_event.id_pk
                                and provided_service.tariff > 0
                                and medical_service.reason_fk = 1 and (medical_service.group_fk != 19
                                    or medical_service.group_fk is NUll)
                        ) = 0 and (
                            select count(1)
                            from provided_service
                                join medical_service
                                    on provided_service.code_fk = medical_service.id_pk
                            where provided_service.event_fk = provided_event.id_pk
                                and provided_service.tariff = 0
                                and medical_service.reason_fk = 1 and (medical_service.group_fk != 19
                                    or medical_service.group_fk is NUll)
                        ) >= 1

                    )
                )
        ) and payment_type_fk != 3
        and (select count(id_pk) from provided_service_sanction
             where service_fk = provided_service.id_pk and error_fk = 34) = 0
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 34)


def drop_outpatient_event(register_element):
    """
        Санкции на случаи поликлиники по заболеваниям со снятыми услугами
    """
    old_query = """
        select T.error_code, provided_service.id_pk
        from provided_service
            join medical_organization department
                on provided_service.department_fk = department.id_pk
            join
                (
                    select provided_event.id_pk as event_id,
                        min(provided_service_sanction.error_fk) as error_code
                    from provided_service ps1
                        join medical_service
                            on medical_service.id_pk = ps1.code_fk
                        join provided_event
                            on ps1.event_fk = provided_event.id_pk
                        join medical_register_record
                            on provided_event.record_fk = medical_register_record.id_pk
                        join medical_register mr1
                            on medical_register_record.register_fk = mr1.id_pk
                        JOIN patient p1
                            on medical_register_record.patient_fk = p1.id_pk
                        join provided_service_sanction
                            on ps1.id_pk = provided_service_sanction.service_fk
                        join medical_error
                            on provided_service_sanction.error_fk = medical_error.id_pk
                                and medical_error.weight = (select max(weight) from medical_error where id_pk in (select error_fk from provided_service_sanction where service_fk = ps1.id_pk))
                    where mr1.is_active
                        and mr1.year = %s
                        and mr1.period = %s
                        and mr1.organization_code = %s
                        and (
                            medical_service.reason_fk = 1
                            and (
                                medical_service.group_fk != 19
                                or medical_service.group_fk is NUll
                            )
                        )
                        and ps1.payment_type_fk = 3
                        group BY provided_event.id_pk
                ) as T
                on provided_service.event_fk = T.event_id
        where provided_service.payment_type_fk <> 3
            --and department.level <> 3
            and (select id_pk from provided_service_sanction
                 where service_fk = provided_service.id_pk
                     and error_fk = T.error_code) is NULL
    """

    new_query = """
    select T.error_code, provided_service.id_pk
    from provided_service
        join medical_organization department
            on provided_service.department_fk = department.id_pk
        JOIN medical_service ms ON ms.id_pk = provided_service.code_fk
        join
            (
                select provided_event.id_pk as event_id,
                    min(provided_service_sanction.error_fk) as error_code
                from provided_service ps1
                    join medical_service
                        on medical_service.id_pk = ps1.code_fk
                    join provided_event
                        on ps1.event_fk = provided_event.id_pk
                    join medical_register_record
                        on provided_event.record_fk = medical_register_record.id_pk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                    JOIN patient p1
                        on medical_register_record.patient_fk = p1.id_pk
                    join provided_service_sanction
                        on ps1.id_pk = provided_service_sanction.service_fk
                    join medical_error
                        on provided_service_sanction.error_fk = medical_error.id_pk
                            and medical_error.weight = (select max(weight) from medical_error where id_pk in (select error_fk from provided_service_sanction where service_fk = ps1.id_pk))
                where mr1.is_active
                    and mr1.year = %s
                    and mr1.period = %s
                    and mr1.organization_code = %s
                    AND (
                           ((medical_service.group_fk not in (19, 27) or medical_service.group_fk is NULL))
                           or
                           (medical_service.group_fk = 19 AND medical_service.subgroup_fk is NOT NULL)
                           )
                    and ps1.payment_type_fk = 3
                    group BY provided_event.id_pk
            ) as T
            on provided_service.event_fk = T.event_id
        LEFT JOIN provided_service_sanction pss
            on pss.service_fk = provided_service.id_pk and pss.error_fk = T.error_code
    where (ms.group_fk != 27 or ms.group_fk is NULL)
        AND pss.id_pk is NULL
    """

    new_query_1 = """
    select T.error_code, provided_service.id_pk
    from provided_service
    JOIN medical_service ms ON ms.id_pk = provided_service.code_fk
    join
        (
            select DISTINCT provided_event.id_pk as event_id,
                pss.error_fk as error_code
            from provided_service ps1
                join medical_service
                    on medical_service.id_pk = ps1.code_fk
                join provided_event
                    on ps1.event_fk = provided_event.id_pk
                join medical_register_record
                    on provided_event.record_fk = medical_register_record.id_pk
                join medical_register mr1
                    on medical_register_record.register_fk = mr1.id_pk
                JOIN patient p1
                    on medical_register_record.patient_fk = p1.id_pk
                join provided_service_sanction pss
                    on pss.id_pk = (
                        select pssi.id_pk
                        from provided_service_sanction pssi
                            join medical_error mei
                                on mei.id_pk = pssi.error_fk
                        WHERE pssi.service_fk = ps1.id_pk
                        ORDER BY mei.weight DESC
                        limit 1
                    )
            where mr1.is_active
                and mr1.year = %s
                and mr1.period = %s
                and mr1.organization_code = %s
                AND (
                       ((medical_service.group_fk not in (19, 27) or medical_service.group_fk is NULL))
                       or
                       (medical_service.group_fk = 19 AND medical_service.subgroup_fk is NOT NULL)
                       )
                and ps1.payment_type_fk = 3
        ) as T
        on provided_service.event_fk = T.event_id
    LEFT JOIN provided_service_sanction pss
        on pss.service_fk = provided_service.id_pk
            and error_fk = T.error_code
    where (ms.group_fk != 27 or ms.group_fk is NULL)
    and pss.id_pk is null
    """

    services = ProvidedService.objects.raw(
        new_query_1, [
            register_element['year'], register_element['period'],
            register_element['organization_code']])

    errors = [(rec.pk, 1, rec.accepted_payment, rec.error_code) for rec in list(services)]
    errors_pk = [rec[0] for rec in errors]

    ProvidedService.objects.filter(pk__in=errors_pk).update(
        accepted_payment=0, payment_type=3)

    errors_objs = []
    for rec in errors:
        errors_objs.append(Sanction(service_id=rec[0], type_id=1,
                                    underpayment=rec[2], error_id=rec[3]))

    Sanction.objects.bulk_create(errors_objs)


def sanctions_on_invalid_hitech_service_diseases(register_element):
    query1 = """
        select ps.id_pk
        from
            provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            LEFT JOIN hitech_service_kind_disease hskd
                on hskd.kind_fk = pe.hitech_kind_fk
                    and hskd.disease_fk = ps.basic_disease_fk
        where
            mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and hskd.id_pk is null
            and mr.type = 2
            and (select id_pk from provided_service_sanction
                 where service_fk = ps.id_pk and error_fk = 77) is null
    """

    query2 = """
        select ps.id_pk
        from provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            LEFT JOIN hitech_service_method_disease hsmd
                on hsmd.method_fk = pe.hitech_method_fk
                    and hsmd.disease_fk = ps.basic_disease_fk
        where
            mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and mr.type = 2
            and hsmd.id_pk is NULL
            and (select id_pk from provided_service_sanction
                 where service_fk = ps.id_pk and error_fk = 78) is null
    """

    services1 = ProvidedService.objects.raw(
        query1, [register_element['year'], register_element['period'],
                 register_element['organization_code']])

    services2 = ProvidedService.objects.raw(
        query2, [register_element['year'], register_element['period'],
                 register_element['organization_code']])

    return get_sanction_tuple(services2, 78) #get_sanction_tuple(services1, 77) +


def sanctions_on_wrong_age_adult_examination(register_element):
    query = """
        select id_pk from provided_service where event_fk in (
        select DISTINCT pe.id_pk
        from provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN patient p
                on p.id_pk = mrr.patient_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            join medical_service ms
                on ms.id_pk = ps.code_fk
        where ms.group_fk IN (7, 25, 26)
            and substr(pe.comment, 5, 1) = '0'
            and (extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk and tariff > 0)) - EXTRACT(YEAR FROM p.birthdate)) not in (
                select DISTINCT age from adult_examination_service
            )
            and mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s)
            and (select id_pk from provided_service_sanction
                 where service_fk = provided_service.id_pk and error_fk = 35) is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 35)


def sanctions_on_adult_examination_service_count(register_element):
    query1 = """
        select id_pk from provided_service where event_fk in (
        select DISTINCT event_id
        from (
            select DISTINCT pe.id_pk event_id, p.birthdate, p.gender_fk,
                (
                    select count(provided_service.id_pk)
                    from provided_service
                        join adult_examination_service aes
                            on aes.stage = 1
                                and aes.gender_fk = p.gender_fk
                                and (aes.is_required or aes.is_one_of)
                                and aes.code_fk = provided_service.code_fk
                                and aes.age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                    WHERE provided_service.event_fk = pe.id_pk
                        and provided_service.payment_type_fk != 3
                ) total,
                (
                    select count(1)
                    from adult_examination_service
                    where stage = 1 and gender_fk = p.gender_fk
                        and is_required
                        and age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                ) required,
                (
                    select count(provided_service.id_pk)
                    from provided_service
                        join adult_examination_service aes
                            on aes.stage = 1
                                and aes.gender_fk = p.gender_fk
                                and aes.is_one_of
                                and aes.code_fk = provided_service.code_fk
                                and aes.age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                    WHERE provided_service.event_fk = pe.id_pk
                        and provided_service.payment_type_fk != 3
                ) one_of

            from provided_service ps
                JOIN medical_service ms
                    on ps.code_fk = ms.id_pk
                join provided_event pe
                    on ps.event_fk = pe.id_pk
                JOIN medical_register_record mrr
                    on mrr.id_pk = pe.record_fk
                JOIN patient p
                    on p.id_pk = mrr.patient_fk
                JOIN medical_register mr
                    on mr.id_pk = mrr.register_fk
            WHERE
                mr.is_active
                and mr.year = %s
                and mr.period = %s
                and mr.organization_code = %s
                and ms.group_fk = 7
        ) as T
        where required > 0 and one_of = 1
            and total < ceil(trunc((required+one_of) * 0.85, 1))
            and (select count(1) from provided_service_sanction
                 where service_fk = provided_service.id_pk and error_fk = 34) = 0
    )
    """

    query2 = """
    select id_pk from provided_service where event_fk in (
        select T.event_id
        from (
            select DISTINCT pe.id_pk event_id,
                (
                    select count(provided_service.id_pk)
                    from provided_service
                        join adult_examination_service aes
                            on aes.stage = 2
                                and aes.gender_fk = p.gender_fk
                                and (aes.is_required or aes.is_one_of)
                                and aes.code_fk = provided_service.code_fk
                                and aes.age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                    WHERE provided_service.event_fk = pe.id_pk
                        and (provided_service.payment_type_fk != 3 or provided_service.payment_type_fk is null)
                ) total,
                (
                    select count(1)
                    from adult_examination_service
                    where stage = 2 and gender_fk = p.gender_fk
                        and is_required
                        and age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                ) required,
                (
                    select count(provided_service.id_pk)
                    from provided_service
                        join adult_examination_service aes
                            on aes.stage = 2
                                and aes.gender_fk = p.gender_fk
                                and aes.is_one_of
                                and aes.code_fk = provided_service.code_fk
                                and aes.age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                    WHERE provided_service.event_fk = pe.id_pk
                        and provided_service.payment_type_fk != 3
                ) one_of

            from provided_service ps
                JOIN medical_service ms
                    on ps.code_fk = ms.id_pk
                join provided_event pe
                    on ps.event_fk = pe.id_pk
                JOIN medical_register_record mrr
                    on mrr.id_pk = pe.record_fk
                JOIN patient p
                    on p.id_pk = mrr.patient_fk
                JOIN medical_register mr
                    on mr.id_pk = mrr.register_fk
            WHERE
                mr.is_active
                and mr.year = %s
                and mr.period = %s
                and mr.organization_code = %s
                and ms.group_fk in (25, 26)
        ) as T
        where required > 0
            and total < ceil(trunc((required+one_of) * 0.85, 1))
            and (select count(1) from provided_service_sanction
                 where service_fk = provided_service.id_pk and error_fk = 34) = 0
    )
    """

    services1 = ProvidedService.objects.raw(
        query1, [register_element['year'], register_element['period'],
                 register_element['organization_code']])

    services2 = ProvidedService.objects.raw(
        query2, [register_element['year'], register_element['period'],
                 register_element['organization_code']])

    return set_sanctions(services1, 34) + set_sanctions(services2, 34)


def sanctions_on_ill_formed_children_examination(register_element):
    query = """
    select id_pk from provided_service where event_fk in (
        select distinct pe1.id_pk
        from provided_service ps1
            join medical_service
                On ps1.code_fk = medical_service.id_pk
            join provided_event pe1
                on ps1.event_fk = pe1.id_pk
            join medical_register_record
                on pe1.record_fk = medical_register_record.id_pk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            JOIN patient p
                on p.id_pk = medical_register_record.patient_fk
        where mr1.is_active
            and mr1.year = %s
            and mr1.period = %s
            and mr1.organization_code = %s
            and ps1.payment_type_fk != 3
            and medical_service.group_fk in (11, 12, 13, 15, 16)
            and (
                (
                    (date_part('year', ps1.end_date) - date_part('year', p.birthdate)) > 3
                    and NOT (
                        (
                            select count(1)
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_primary
                                and ps2.payment_type_fk = 2
                        ) = 1 and EXISTS (
                            select 1
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_specialist
                                and ps2.payment_type_fk = 2
                        )
                    )
                ) OR (
                    (date_part('year', ps1.end_date) - date_part('year', p.birthdate)) <= 3
                    and NOT (
                        (
                            select count(1)
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_primary
                                and ps2.payment_type_fk = 2
                        ) = 1
                    )
                )
            )
        ) and payment_type_fk != 3
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 34)


def sanctions_on_wrong_examination_attachment(register_element):
    query = """
        select distinct ps1.id_pk--, 1, ps1.invoiced_payment, 1
        from provided_service ps1
            join medical_service
                On ps1.code_fk = medical_service.id_pk
            join provided_event pe1
                on ps1.event_fk = pe1.id_pk
            join medical_register_record
                on pe1.record_fk = medical_register_record.id_pk
            join medical_register mr1
                on medical_register_record.register_fk = mr1.id_pk
            JOIN patient p1
                on medical_register_record.patient_fk = p1.id_pk
            join insurance_policy
                on p1.insurance_policy_fk = insurance_policy.version_id_pk
            join person
                on person.version_id_pk = (
                    select version_id_pk
                    from person where id = (
                        select id
                        from person
                        where version_id_pk = insurance_policy.person_fk
                    ) and is_active
                )
            join attachment
                on attachment.id_pk = (
                    select max(id_pk)
                    from attachment
                    where person_fk = person.version_id_pk and status_fk = 1
                        and confirmation_date <= (
                            select max(end_date)
                            from provided_service
                            where event_fk = pe1.id_pk
                        )
                        and attachment.is_active
                )
            join medical_organization medOrg
                on (
                    medOrg.id_pk = attachment.medical_organization_fk and
                    medOrg.parent_fk is null
                ) or medOrg.id_pk = (
                    select parent_fk
                    from medical_organization
                    where id_pk = attachment.medical_organization_fk
                )
        WHERE mr1.is_active
            and mr1.year = %s
            and mr1.period = %s
            and mr1.organization_code = %s
            and mr1.organization_code != medOrg.code
            and (select id_pk from provided_service_sanction
                 where service_fk = ps1.id_pk and error_fk = 1) is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 1)


def sanctions_on_wrong_age_examination_children_adopted(register_element):
    query = """
        select ps.id_pk
        from provided_service ps
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join provided_event pe
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN patient p
                on p.id_pk = mrr.patient_fk
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and (
                (ms.code in ('119220', '119221') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 0 and 2) or
                (ms.code in ('119222', '119223') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 3 and 4) or
                (ms.code in ('119224', '119225') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 5 and 6) or
                (ms.code in ('119226', '119227') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 7 and 13) or
                (ms.code in ('119228', '119228') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) = 14) or
                (ms.code in ('119230', '119231') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 15 and 17)
            ) and (select count(1) from provided_service_sanction where service_fk = ps.id_pk and error_fk = 35) = 0
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 35)


def sanctions_on_wrong_age_examination_children_difficult(register_element):
    query = """
        select ps.id_pk
        from provided_service ps
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join provided_event pe
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN patient p
                on p.id_pk = mrr.patient_fk
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and (
                (ms.code in ('119020', '119021') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 0 and 2) or
                (ms.code in ('119022', '119023') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 3 and 4) or
                (ms.code in ('119024', '119025') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 5 and 6) or
                (ms.code in ('119026', '119027') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 7 and 13) or
                (ms.code in ('119028', '119028') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) = 14) or
                (ms.code in ('119030', '119031') and not (date_part('year', ps.end_date) - date_part('year', p.birthdate)) between 15 and 17)
            ) and (select count(1) from provided_service_sanction where service_fk = ps.id_pk and error_fk = 35) = 0
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    return set_sanctions(services, 35)


def sanctions_on_wrong_gender_examination(register_element):
    query = """
            select
            distinct ps.id_pk
            from medical_register mr
            JOIN medical_register_record mrr
                 ON mr.id_pk=mrr.register_fk
            JOIN provided_event pe
                 ON mrr.id_pk=pe.record_fk
            JOIN provided_service ps
                 ON ps.event_fk=pe.id_pk
            JOIN medical_service ms
                 ON ms.id_pk = ps.code_fk
            JOIN patient pt
                 ON mrr.patient_fk = pt.id_pk
            where mr.is_active
                 and mr.year = %(year)s
                 and mr.period = %(period)s
                 and mr.organization_code = %(organization)s
                 and ms.group_fk in (11, 12, 13, 9, 7)
                 and (ms.examination_primary or ms.examination_final)
                 and ms.is_cost
                 and pt.gender_fk != ms.gender_fk
                 and ps.payment_type_fk = 2
            """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    return get_sanction_tuple(services, 41)


def drop_duplicate_examination_in_current_register(register_element):
    query = """
        select ps.id_pk
        from provided_event pe
            JOIN (
                select record_fk, count(*)
                from provided_event where id_pk in (
                    select DISTINCT pe.id_pk
                    from provided_service ps
                        join medical_service ms
                            on ms.id_pk = ps.code_fk
                        JOIN provided_event pe
                            on pe.id_pk = ps.event_fk
                        JOIN medical_register_record mrr
                            on mrr.id_pk = pe.record_fk
                        JOIN medical_register mr
                            ON mr.id_pk = mrr.register_fk
                    WHERE mr.is_active
                        and mr.year = %(year)s
                        and mr.period = %(period)s
                        and mr.organization_code = %(organization)s
                        and ms.group_fk in (7, 9, 12, 13, 15, 16)
                        and ps.payment_type_fk = 2
                )
                group by record_fk
                having count(*) > 1
            ) as T1 on pe.id_pk = (select max(id_pk) from provided_event where record_fk = T1.record_fk)

            join provided_service ps
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on pe.record_fk = mrr.id_pk
            JOIN patient p
                on p.id_pk = mrr.patient_fk

    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    return set_sanctions(services, 64)


def sanctions_on_service_term_kind_mismatch(register_element):
    query = """
        select ps.id_pk
        from provided_service ps
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join provided_event pe
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            LEFT JOIN provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 79
        where mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and pss.id_pk is null
            and NOT (
                (pe.term_fk = 1 and pe.kind_fk in (3, 4, 10, 11 ))
                or (pe.term_fk = 2 and pe.kind_fk in (3, 10, 11))
                OR (pe.term_fk = 3 and pe.kind_fk in (1, 4, 5, 6, 7))
                or (pe.term_fk = 4 and pe.kind_fk in (2, 8, 9))
            )
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    return set_sanctions(services, 79)


def sanctions_on_service_term_mismatch(register_element):
    query = """
        select ps.id_pk
        from provided_service ps
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join provided_event pe
                on ps.event_fk = pe.id_pk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN tariff_profile tp
                on tp.id_pk = ms.tariff_profile_fk
            LEFT JOIN provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 76
        where mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and pss.id_pk is null
            and pe.term_fk in (1, 2)
            and tp.term_fk != pe.term_fk
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    #print len(services) #, type(services)

    return set_sanctions(services, 76)


def drop_second_phase_examination(register_element):
    query = """
        select ps.id_pk
        from medical_register mr JOIN medical_register_record mrr ON mr.id_pk=mrr.register_fk
            JOIN provided_event pe ON mrr.id_pk=pe.record_fk
            JOIN provided_service ps ON ps.event_fk=pe.id_pk
            JOIN medical_service ms ON ms.id_pk = ps.code_fk
            join patient pt ON pt.id_pk = mrr.patient_fk
            JOIN insurance_policy ip ON ip.version_id_pk = pt.insurance_policy_fk
            join
                (
                    select distinct mr1.id_pk as mr_id, ip1.id as ip_id

                    from provided_service ps1
                        join medical_service
                            on medical_service.id_pk = ps1.code_fk
                        join provided_event
                            on ps1.event_fk = provided_event.id_pk
                        join medical_register_record
                            on provided_event.record_fk = medical_register_record.id_pk
                        join medical_register mr1
                            on medical_register_record.register_fk = mr1.id_pk
                        JOIN patient p1
                            on medical_register_record.patient_fk = p1.id_pk
                        JOIN insurance_policy ip1 ON ip1.version_id_pk = p1.insurance_policy_fk

                        where
                             mr1.year = %(year)s
                             and mr1.period = %(period)s
                             and mr1.organization_code = %(organization)s
                             and ps1.payment_type_fk = 3
                             AND medical_service.group_fk = 7
                        group BY mr_id, ip_id
                ) as T
                on ip.id = T.ip_id and mr.id_pk = T.mr_id
        where
            ms.group_fk in (25, 26)
            and ps.payment_type_fk = 2
            and (select id_pk from provided_service_sanction
                 where service_fk = ps.id_pk and error_fk = 34) is null
    """
    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    #print len(services) #, type(services)

    return get_sanction_tuple(services, 34)


def main():
    COMMENT_COEFFICIENT_CURATION = re.compile(r'[0-1]{6}1')
    min_date_for_stopped_policy = datetime.strptime('2011-01-01', '%Y-%m-%d').date()

    register_element = get_register_element()
    while register_element:
        start = time.clock()
        print register_element
        errors = []

        current_period = '%s-%s-01' % (register_element['year'],
                                       register_element['period'])
        current_period = datetime.strptime(current_period, '%Y-%m-%d').date()
        set_status(register_element, 11)
        if register_element['status'] == 1:
            ProvidedServiceCoefficient.objects.filter(
                service__event__record__register__is_active=True,
                service__event__record__register__year=register_element['year'],
                service__event__record__register__period=register_element['period'],
                service__event__record__register__organization_code=register_element['organization_code']
            ).delete()

            Sanction.objects.filter(
                service__event__record__register__is_active=True,
                service__event__record__register__year=register_element['year'],
                service__event__record__register__period=register_element['period'],
                service__event__record__register__organization_code=register_element['organization_code']
            ).delete()

            ProvidedService.objects.filter(
                event__record__register__is_active=True,
                event__record__register__year=register_element['year'],
                event__record__register__period=register_element['period'],
                event__record__register__organization_code=register_element['organization_code']
            ).update(payment_type=None)

            identify_patient(register_element)
            update_patient_attacment_code(register_element)
            update_payment_kind(register_element)

            print u'repeated service'
            sanctions_on_repeated_service(register_element)
            print u'wrong date'
            sanctions_on_wrong_date_service(register_element)
            #print u'repeated examination'
            #sanctions_on_repeated_examination(register_element)
            print u'duplicate'
            sanctions_on_duplicate_services(register_element)
            print u'cross dates'
            sanctions_on_cross_dates_services(register_element)
            print u'disease_gender'
            sanctions_on_disease_gender(register_element)
            print u'service gender'
            sanctions_on_service_gender(register_element)
            print u'wrong age'
            sanctions_on_wrong_age_service(register_element)
            print u'not paid'
            sanctions_on_not_paid_in_oms(register_element)
            print u'invalid hitech service disease'
            sanctions_on_invalid_hitech_service_diseases(register_element)
            print u'wrong_age_adult_examination'
            sanctions_on_wrong_age_adult_examination(register_element)
            print u'wrong_age_examination_age_group'
            sanctions_on_wrong_examination_age_group(register_element)
            print u'sanctions_on_wrong_age_examination_children_adopted'
            sanctions_on_wrong_age_examination_children_adopted(register_element)
            print u'sanctions_on_wrong_age_examination_children_difficult'
            sanctions_on_wrong_age_examination_children_difficult(register_element)
            print u'sanctions_on_wrong_gender_examination'
            sanctions_on_wrong_gender_examination(register_element)
            #print u'wrong_examination_attachment'
            #sanctions_on_wrong_examination_attachment(register_element)
            #sanctions_on_incorrect_examination(register_element)
            sanctions_on_service_term_mismatch(register_element)
            sanctions_on_service_term_kind_mismatch(register_element)

            print u'drop_second_phase_examination'
            drop_second_phase_examination(register_element)

        print 'iterate tariff', register_element
        with transaction.atomic():
            for row, service in enumerate(get_services(register_element)):
                if row % 1000 == 0:
                    print row
                #print '$$$', dir(service), service.payment_type
                if not service.payment_type_id:

                    if not service.patient_policy:
                        set_sanction(service, 54)

                    elif service.person_deathdate \
                            and service.person_deathdate < service.start_date:
                        set_sanction(service, 56)

                    elif service.policy_stop_date:
                        if service.policy_stop_date < service.start_date \
                                and service.stop_reason in (1, 3, 4):
                            set_sanction(service, 53)

                        if service.policy_type == 1 and service.policy_stop_date < \
                                min_date_for_stopped_policy:
                            set_sanction(service, 54)

                    #if not service.service_examination_special and \
                    #        is_wrong_date(service, current_period):
                    #    set_sanction(service, 32)

                    #if register_element['status'] == 1 \
                    #        and service.service_group not in (11, 9) \
                    #        and is_wrong_age(service):
                    #    set_sanction(service, 35)

                    #if service.service_examination_group and \
                    #        is_wrong_examination_age_group(service):
                    #    set_sanction(service, 35)

                provided_tariff = float(service.tariff)

                if service.alternate_tariff:
                    tariff = float(service.alternate_tariff)
                else:
                    tariff = float(service.expected_tariff or 0)

                term = service.service_term
                nkd = service.nkd or 1

                ### Выбор nkd для РСЦ и ПСО
                if service.service_code in ('098958', '098959'):
                    nkd = 12
                elif service.service_code in ('098960', '098961'):
                    nkd = 12
                elif service.service_code in ('098962', '098963'):
                    nkd = 7
                elif service.service_code in ('098964', '098965'):
                    nkd = 30
                elif service.service_code in ('098966', '098967'):
                    nkd = 30
                elif service.service_code in ('098968', '098969'):
                    nkd = 30

                ### Неонатология 11 - я группа
                if service.service_group == 20 and service.vmp_group == 11:
                    nkd = 70

                '''
                if service.service_tariff_profile == 11 and service.organization_code == '280043':
                    nkd = 19
                '''

                if service.service_group in (3, 5):
                    term = 3

                if term in (1, 2):
                    days = float(service.quantity)

                    is_endovideosurgery = (service.comment and
                                           len(service.comment) == 6 and
                                           service.comment[0] == '1')

                    if term == 1:
                        duration_coefficient = 70
                        if service.service_group == 20:
                            duration_coefficient = 90
                        # КСГ 76, 77, 78
                        if service.service_code in (
                                '098964', '098965', '098966',
                                '098967', '098968', '098969'):
                            duration_coefficient = 50

                        if is_endovideosurgery or service.service_code in ('098913', '098940'):
                            duration_coefficient = 0
                        if service.service_group == 20 and service.vmp_group not in (5, 10, 11, 14, 18, 30):
                            duration_coefficient = 0

                        if service.service_group == 2 and \
                                len(service.comment) == 8 and \
                                service.comment[7] == '1':
                            duration_coefficient = 0

                        if (service.organization_code == '280013' and service.service_tariff_profile in (24, 30)) or \
                                (service.organization_code == '280005' and service.service_tariff_profile in (24, 67)):
                            duration_coefficient = 50

                    elif term == 2:
                        duration_coefficient = 90
                        if is_endovideosurgery:
                            duration_coefficient = 50

                    '''
                    if service.service_code == '098901':
                        print service.service_code, duration_coefficient, nkd, is_endovideosurgery
                    '''

                    '''
                    if term == 1:
                        duration_coefficient = 80
                        if service.service_tariff_profile == 24:
                            duration_coefficient = 50
                        if is_endovideosurgery:
                            duration_coefficient = 0

                    elif term == 2:
                        duration_coefficient = 90
                        if is_endovideosurgery:
                            duration_coefficient = 50

                    if service.service_group in (1, 2):
                        duration_coefficient = 50

                    if service.service_group == 20:

                        if service.service_code in (
                                "023040", "123040", "023047", "123047",
                                "023091", "123091", "123097", "123098"):

                            duration_coefficient = 90

                        else:
                            duration_coefficient = 0

                        if service.end_date < date(2014, 4, 1):
                            duration_coefficient = 50
                    #P05.0, P05.1,
                    if service.service_tariff_profile == 56:
                        duration_coefficient = 0

                    if service.service_tariff_profile == 31 and service.end_date >= date(2014, 8, 1):
                        duration_coefficient = 0

                    if service.service_tariff_profile == 58:
                        duration_coefficient = 90

                    if service.basic_disease_id in (7124, 7125, 7128, 7129,
                                                    7130, 7131, 7132, ):
                        nkd = 70
                    '''

                    duration = (days / float(nkd)) * 100

                    if duration < duration_coefficient:
                        tariff = round(tariff / float(nkd) * float(service.quantity), 2)

                    if service.service_tariff_profile == 999:
                        if service.service_code != '098710':
                            tariff = 0

                    accepted_payment = tariff

                    if term == 1:
                        # Коэффициент курации
                        if service.quantity >= nkd * 2 and service.service_group != 20 \
                                and COMMENT_COEFFICIENT_CURATION.match(service.comment):
                            accepted_payment += round(accepted_payment * 0.25, 2)
                            provided_tariff += round(provided_tariff * 0.25, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=7)

                        # Коэффициенты КПГ
                        if service.service_tariff_profile == 36 and \
                                (service.level == 1 or service.organization_code in ('280027', '280075')):
                            accepted_payment += round(accepted_payment * 0.38, 2)
                            provided_tariff += round(provided_tariff * 0.38, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=8)

                        if service.service_tariff_profile == 10:
                            accepted_payment += round(accepted_payment * 0.34, 2)
                            provided_tariff += round(provided_tariff * 0.34, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=9)

                        if service.service_tariff_profile == 28 and \
                                service.organization_code == "280064":
                            accepted_payment += round(accepted_payment * 0.65, 2)
                            provided_tariff += round(provided_tariff * 0.65, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=10)

                        if service.service_tariff_profile == 37 and \
                                service.organization_code == "280064":
                            accepted_payment += round(accepted_payment * 0.8, 2)
                            provided_tariff += round(provided_tariff * 0.8, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=11)

                        if service.service_tariff_profile == 38 and \
                                service.organization_code == "280064":
                            accepted_payment += round(accepted_payment * 0.47, 2)
                            provided_tariff += round(provided_tariff * 0.47, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=12)

                        if service.service_group == 2 and \
                                len(service.comment) == 8 and \
                                service.comment[7] == '1':
                            accepted_payment -= round(accepted_payment * 0.4, 2)
                            provided_tariff -= round(provided_tariff * 0.4, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=13)

                        if service.service_code in ('098901', '198901', '098912', '198912') and \
                                service.organization_code in ('280084', '280027') and \
                                len(service.comment) == 8 and \
                                service.comment[7] == '1':
                            accepted_payment += round(accepted_payment * 0.3, 2)
                            provided_tariff += round(provided_tariff * 0.3, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=14)

                        if service.service_code in ('098901', '198901', '098912', '198912') and \
                                service.organization_code in ('280084', '280027') and \
                                len(service.comment) == 9 and \
                                service.comment[8] == '1':
                            accepted_payment += round(accepted_payment * 1, 2)
                            provided_tariff += round(provided_tariff * 1, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=15)
                    # Новые коффициенты по медицинской реабилитации в дневном стационаре
                    if term == 2:
                        if service.service_tariff_profile == 50 and \
                                service.organization_code in ("280064", "280003"):
                            accepted_payment += round(accepted_payment * 0.2, 2)
                            provided_tariff += round(provided_tariff * 0.2, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=16)

                        if service.service_tariff_profile == 2 and \
                                service.organization_code in ("280064", "280003"):
                            accepted_payment += round(accepted_payment * 0.1, 2)
                            provided_tariff += round(provided_tariff * 0.1, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=17)

                        if service.service_tariff_profile == 41 and \
                                service.organization_code in ("280064", "280003"):
                            accepted_payment += round(accepted_payment * 0.4, 2)
                            provided_tariff += round(provided_tariff * 0.4, 2)
                            ProvidedServiceCoefficient.objects.get_or_create(
                                service=service, coefficient_id=18)


                    '''
                    if service.is_agma_cathedra and term == 1:
                        accepted_payment += round(accepted_payment * 0.015, 2)
                        provided_tariff += round(provided_tariff * 0.015, 2)
                        ProvidedServiceCoefficient.objects.create(
                            service=service, coefficient_id=2)
                    '''

                elif term == 3 or term is None:
                    quantity = service.quantity or 1

                    comment = service.comment
                    is_single_visit = (comment and len(comment) == 6 and
                                       comment[5] == '1')
                    is_mobile_brigade = (comment and len(comment) == 6 and comment[4] == '1')

                    single_visit_exception_group = (7, 8, 25, 26, 9, 10, 11, 12,
                                                    13, 14, 15, 16)
                    if service.service_group in (29, ):
                        accepted_payment = tariff
                    else:
                        accepted_payment = tariff * float(quantity)
                        tariff *= float(quantity)

                    '''
                    if (is_single_visit or service.reason_code == 3) and not \
                            (service.reason_code in (1, 4, 5) or service.service_group in single_visit_exception_group):

                        accepted_payment -= round(accepted_payment * 0.6, 2)
                        provided_tariff -= round(provided_tariff * 0.6, 2)
                        ProvidedServiceCoefficient.objects.create(
                            service=service, coefficient_id=3)
                    '''

                    if is_mobile_brigade and service.service_group in (7, 25, 26,  11, 15, 16,  12, 13,  4):
                        accepted_payment += round(accepted_payment * 0.07, 2)
                        provided_tariff += round(provided_tariff * 0.07, 2)
                        ProvidedServiceCoefficient.objects.get_or_create(
                            service=service, coefficient_id=5)

                    if service.coefficient_4:
                        accepted_payment += round(accepted_payment * 0.2, 2)
                        provided_tariff += round(provided_tariff * 0.2, 2)
                        ProvidedServiceCoefficient.objects.get_or_create(
                            service=service, coefficient_id=4)

                elif service.event.term_id == 4:
                    quantity = service.quantity or 1
                    accepted_payment = tariff * float(quantity)
                    provided_tariff *= float(quantity)
                else:
                    raise ValueError(u'Strange term')

                service.calculated_payment = accepted_payment
                service.provided_tariff = provided_tariff

                if (tariff - float(service.tariff)) >= 0.01 or \
                        (tariff - float(service.tariff)) <= -0.01:
                    set_sanction(service, 61)
                else:
                    service.accepted_payment = round(float(accepted_payment), 2)
                    if not service.payment_type:
                        service.payment_type_id = 2

                service.save()

        print u'stomat, outpatient, examin'
        if register_element['status'] == 500:
            sanctions_on_repeated_service(register_element)
            #sanctions_on_invalid_stomatology_event(register_element)
            #drop_outpatient_event(register_element)
            #sanctions_on_invalid_outpatient_event(register_element)
            #drop_examination_event(register_element)
            #sanctions_on_ill_formed_children_examination(register_element)
            drop_duplicate_examination_in_current_register(register_element)
        else:
            sanctions_on_invalid_stomatology_event(register_element)
            #sanctions_on_wrong_examination_age_group(register_element)
            sanctions_on_repeated_service(register_element)
            drop_outpatient_event(register_element)
            sanctions_on_invalid_outpatient_event(register_element)
            drop_examination_event(register_element)
            sanctions_on_ill_formed_children_examination(register_element)
            #sanctions_on_adult_examination_service_count(register_element)
            sanctions_on_ill_formed_adult_examination(register_element)
            drop_duplicate_examination_in_current_register(register_element)

        """
        errors_pk = [rec[0] for rec in errors]
        ProvidedService.objects.filter(pk__in=errors_pk).update(
            accepted_payment=0, payment_type_id=3)

        errors_objs = []
        for rec in errors:
            errors_objs.append(Sanction(service_id=rec[0], type=1,
                                        underpayment=rec[2], error_id=rec[3]))

        Sanction.objects.bulk_create(errors_objs)
        """
        print Sanction.objects.filter(
            service__event__record__register__is_active=True,
            service__event__record__register__year=register_element['year'],
            service__event__record__register__period=register_element['period'],
            service__event__record__register__organization_code=register_element['organization_code']
        ).count()

        if register_element['status'] == 1:
            set_status(register_element, 3)
        elif register_element['status'] in (5, 500):
            set_status(register_element, 8)

        elapsed = time.clock() - start
        print register_element['organization_code'], \
            u'Время выполнения: {0:d} мин {1:d} сек'.format(int(elapsed//60), int(elapsed % 60))

        register_element = get_register_element()


class Command(BaseCommand):
    help = u'Проводим МЭК'

    def handle(self, *args, **options):
        main()
