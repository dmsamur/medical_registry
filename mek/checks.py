# -*- coding: utf-8 -*-

from django.db import transaction
from django.db.models import Q, F
from main.funcs import howlong
from main.models import Sanction, SanctionStatus, ProvidedService


def set_sanction(service, error_code):
    service.payment_type_id = 3
    service.accepted_payment = 0
    service.save()

    sanction = Sanction.objects.create(
        type_id=1, service=service, underpayment=service.invoiced_payment,
        is_active=True,
        error_id=error_code)

    SanctionStatus.objects.create(
        sanction=sanction,
        type=SanctionStatus.SANCTION_TYPE_ADDED_BY_MEK)


def set_sanctions(service_qs, error_code):
    with transaction.atomic():
        for service in service_qs:
            set_sanction(service, error_code)


@howlong
def underpay_repeated_service(register_element):
    """
        Санкции на повторно поданные услуги
    """

    query = """
        with current_period as (select format('%%s-%%s-01', %(year)s, %(period)s)::DATE as val)

        select DISTINCT ps.id_pk from (
        select ps.id_pk as service_id,
            ps.event_fk as event_id,

            row_number() over (PARTITION BY i.id, ps.code_fk, ps.end_date, ps.start_date,
            ps.basic_disease_fk, ps.worker_code, p.newborn_code order by format('%%s-%%s-01', mr.year, mr.period)::DATE) as rnum_repeated,

            row_number() over (PARTITION BY i.id, ps.code_fk, ps.end_date, ps.start_date,
            ps.basic_disease_fk, ps.worker_code, p.newborn_code, mr.year, mr.period order by ps.id_pk) as rnum_duplicate,

            format('%%s-%%s-01', mr.year, mr.period)::DATE as checking_period
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
            and format('%%s-%%s-01', mr.year, mr.period)::DATE between (select val from current_period) - interval '4 months' and (select val from current_period)
            and (ps.payment_type_fk = 2 or ps.payment_type_fk is NULL)
        ) as T
        join provided_service ps
            on ps.id_pk = T.service_id
        where checking_period = (select val from current_period) and rnum_repeated > 1 and rnum_duplicate = 1
            AND (select count(pss.id_pk) from provided_service_sanction pss
                 where pss.service_fk = T.service_id and pss.error_fk = 64) = 0
    """
    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 64)


@howlong
def underpay_repeated_examination(register_element):
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

    set_sanctions(services1, 64)
    set_sanctions(services2, 64)


@howlong
def underpay_ill_formed_adult_examination(register_element):
    """
        Санкции на взрослую диспансеризацю у которой в случае
        не хватает услуг (должна быть 1 платная и больше 0 бесплатных)
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
                                and ms2.group_fk in (7, 9)
                        ) as primary_count,
                        (
                            select count(1)
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_specialist
                                and ps2.payment_type_fk = 2
                                and ms2.group_fk in (7, 9)
                        ) as specialist_count,
                        (
                            select count(1)
                            from provided_service ps2
                                join medical_service ms2
                                    on ms2.id_pk = ps2.code_fk
                            WHERE ps2.event_fk = pe1.id_pk
                                and ms2.examination_final
                                and ps2.payment_type_fk = 2
                                and ms2.group_fk in (7, 9)
                        ) as finals_count
                from provided_event pe1
                    join medical_register_record
                        on pe1.record_fk = medical_register_record.id_pk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                where mr1.is_active
                    and mr1.year = %s
                    and mr1.period = %s
                    and mr1.organization_code = %s
                    --and medical_service.group_fk in (7, 9)
                    --and pss.id_pk is NULL
                    and pe1.end_date < '2015-06-01'
            ) as T
            join provided_service ps
                on ps.event_fk = T.id_pk
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            LEFT join provided_service_sanction pss
               on pss.service_fk = ps.id_pk and pss.error_fk = 34
        where ms.group_fk in (7, 9)
            and (primary_count != 1 or specialist_count = 0 or finals_count != 1)
            and pss.id_pk is null
            and (ps.payment_type_fk != 3 or ps.payment_type_fk is null)

    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 34)


@howlong
def underpay_duplicate_services(register_element):
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
            join medical_service ms
                on ms.id_pk = ps.code_fk
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
            LEFT JOIN provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 67
        where mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and (ms.group_fk != 27 or ms.group_fk is null)
            and pss.id_pk is null
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

    set_sanctions(services, 67)


@howlong
def underpay_cross_dates_services(register_element):
    """
        Санкции на пересечения дней в отделениях
        Поликлиника в стационаре
        И стационар в стационаре
    """
    query1 = """
        select ps.id_pk
        FROM provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_register_record mrr
                on pe.record_fk = mrr.id_pk
            join medical_register mr
                on mrr.register_fk = mr.id_pk
            join medical_service ms
                on ms.id_pk = ps.code_fk
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
                    and (ms.group_fk not in (27, 5, 3)
                         or ms.group_fk is null
                         )
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
            and (ms.group_fk != 27 or ms.group_fk IS NULL)
            and (select count(1) from provided_service_sanction where service_fk = ps.id_pk and error_fk = 73) = 0
        order by ps.id_pk
    """

    query2 = """
        select ps.id_pk
        FROM provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_register_record mrr
                on pe.record_fk = mrr.id_pk
            join medical_register mr
                on mrr.register_fk = mr.id_pk
            join medical_service ms
                on ms.id_pk = ps.code_fk
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
                    and (ms.group_fk not in (27, 5, 3)
                         or ms.group_fk is null
                         )
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
            and (ms.group_fk != 27 or ms.group_fk IS NULL)
            and (select count(1) from provided_service_sanction where service_fk = ps.id_pk and error_fk = 73) = 0
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

    set_sanctions(services1, 73)
    set_sanctions(services2, 73)


@howlong
def underpay_disease_gender(register_element):
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

    set_sanctions(services, 29)


@howlong
def underpay_service_gender(register_element):
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


@howlong
def underpay_wrong_date_service(register_element):
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
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 32
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and (
                ((ps.end_date < (format('%%s-%%s-01', mr.year, mr.period)::DATE - interval '2 month') and not mrr.is_corrected and not ms.examination_special)
                or (ps.end_date < (format('%%s-%%s-01', mr.year, mr.period)::DATE - interval '3 month') and mrr.is_corrected and not ms.examination_special)
                or (ps.end_date >= format('%%s-%%s-01', mr.year, mr.period)::DATE + interval '1 month')
                ) or (
                    ms.examination_special = True and ms.code <> '019014'
                        and age(format('%%s-%%s-01', mr.year, mr.period)::DATE - interval '1 month', ps.end_date) > '1 year'
                ) or (
                    ms.code in ('019014')
                    and age(format('%%s-%%s-01', mr.year, mr.period)::DATE - interval '1 month', ps.end_date) > '2 year'
                )
            )
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 32)


@howlong
def underpay_wrong_age_service(register_element):
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
            LEFT JOIN provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 35
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and (ms.group_fk NOT in (20, 7, 9, 10, 11, 12, 13, 14, 15, 16) or ms.group_fk is NULL) AND
                  NOT(ms.code between '001441' and '001460' or
                         ms.code in ('098703', '098770', '098940', '098913', '098914', '098915', '019018'))
            and (
                (age(ps.start_date, p.birthdate) < '18 year' and substr(ms.code, 1, 1) = '0')
                or (age(ps.start_date, p.birthdate) >= '18 year' and substr(ms.code, 1, 1) = '1'))
            and pss.id_pk is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 35)


@howlong
def underpay_wrong_examination_age_group(register_element):
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
            LEFT JOIN provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 35
        WHERE mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and pe.end_date < '2015-06-01'
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
            and pss.id_pk is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 35)


@howlong
def underpay_not_paid_in_oms(register_element):
    """
        Санкции на диагнозы и услуги не оплачиваемые по ТП ОМС
    """
    services1 = ProvidedService.objects.filter(
        basic_disease__is_paid=False,
        event__record__register__is_active=True,
        event__record__register__year=register_element['year'],
        event__record__register__period=register_element['period'],
        event__record__register__organization_code=register_element['organization_code'],
    ).filter(~Q(event__record__register__organization_code='280043'))\
     .extra(where=['(select count(id_pk) from provided_service_sanction where service_fk = provided_service.id_pk and error_fk = 58) = 0'])

    services2 = ProvidedService.objects.filter(
        code__is_paid=False,
        event__record__register__is_active=True,
        event__record__register__year=register_element['year'],
        event__record__register__period=register_element['period'],
        event__record__register__organization_code=register_element['organization_code']
    ).extra(where=['(select count(id_pk) from provided_service_sanction where service_fk = provided_service.id_pk and error_fk = 59) = 0'])

    set_sanctions(services1, 58)
    set_sanctions(services2, 59)


@howlong
def underpay_examination_event(register_element):
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

    query = '''
            SELECT provided_service.id_pk, 1, accepted_payment, T.error_id
            FROM provided_service
            JOIN (
                SELECT pe1.id_pk AS event_id,
                pss.error_fk AS error_id,
                COUNT(DISTINCT CASE WHEN ps1.payment_type_fk = 3
                                         AND (ms.examination_primary OR ms.examination_final)
                                      THEN ps1.id_pk
                               END) AS excluded_services,
                COUNT(DISTINCT CASE WHEN ps1.payment_type_fk = 2
                                      THEN ps1.id_pk
                               END) AS accepted_services
                FROM provided_service ps1
                    JOIN medical_service ms
                       ON ms.id_pk = ps1.code_fk
                    JOIN provided_event pe1
                       ON ps1.event_fk = pe1.id_pk
                    JOIN medical_register_record
                       ON pe1.record_fk = medical_register_record.id_pk
                    JOIN medical_register mr1
                       ON medical_register_record.register_fk = mr1.id_pk
                    LEFT JOIN provided_service_sanction pss
                        ON pss.id_pk = (
                              SELECT in_pss.id_pk
                              FROM provided_service in_ps
                                  JOIN provided_service_sanction in_pss
                                     ON in_ps.id_pk = in_pss.service_fk
                                  JOIN medical_error in_me
                                     ON in_me.id_pk = in_pss.error_fk
                              WHERE in_ps.event_fk = ps1.event_fk
                                    AND in_pss.is_active
                              ORDER BY in_me.weight DESC
                              LIMIT 1
                        )
                WHERE mr1.is_active
                   AND mr1.year = %s
                   AND mr1.period = %s
                   AND mr1.organization_code = %s
                   AND ms.group_fk IN (7, 9, 11, 12, 13, 15, 16)
                GROUP BY event_id, error_id
              ) AS T
               ON T.event_id = provided_service.event_fk
            LEFT JOIN provided_service_sanction
               ON provided_service_sanction.service_fk = provided_service.id_pk
                  AND provided_service_sanction.error_fk = T.error_id
            WHERE provided_service_sanction.id_pk IS NULL
                  AND T.excluded_services > 0
                  AND T.accepted_services > 0
    '''

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    errors = [(rec.pk, 1, rec.accepted_payment, rec.error_id) for rec in list(services)]
    errors_pk = [rec[0] for rec in errors]

    ProvidedService.objects.filter(pk__in=errors_pk).update(
        accepted_payment=0, payment_type=3)

    with transaction.atomic():
        for rec in errors:
            set_sanction(ProvidedService.objects.get(pk=rec[0]), rec[3])


@howlong
def underpay_invalid_stomatology_event(register_element):
    """
        Санкции на неверно оформленные случаи стоматологии
    """
    old_query = """
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
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps1.id_pk and pss.error_fk = 34
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
    """

    query = """
        select ps.id_pk
        FROM (
                select
                    pe.id_pk as event_id,
                    ps.end_date,
                    ps.start_date,
                    sum(
                        case when ms.subgroup_fk is NULL
                                and ms.group_fk = 19
                                and ms.subgroup_fk is null
                        THEN 1
                        ELSE 0
                        END
                    ) as service,
                    sum(
                        case when ms.subgroup_fk in (12, 13, 14, 17)
                        then 1
                        else 0
                        end
                    ) as admission
                from provided_service ps
                    join medical_service ms
                        On ps.code_fk = ms.id_pk
                    left join medical_service_subgroup msg
                        on ms.subgroup_fk = msg.id_pk
                    join provided_event pe
                        on ps.event_fk = pe.id_pk
                    join medical_register_record
                        on pe.record_fk = medical_register_record.id_pk
                    join patient p1
                        on p1.id_pk = medical_register_record.patient_fk
                    join medical_register mr1
                        on medical_register_record.register_fk = mr1.id_pk
                    LEFT join provided_service_sanction pss
                        on pss.service_fk = ps.id_pk and pss.error_fk = 34
                where mr1.is_active
                    and mr1.year = %(year)s
                    and mr1.period = %(period)s
                    and mr1.organization_code = %(organization)s
                    and (ms.group_fk = 19 or (ms.subgroup_fk in (12, 13, 14, 17) and ms.group_fk is null))
                GROUP BY pe.id_pk, ps.end_date, ps.start_date
            ) as T
            join provided_service ps
                on ps.event_fk = T.event_id
        where
            (admission > 1
            or service = 0
            or admission = 0)
            and (select count(*) from provided_service_sanction
                 where service_fk = ps.id_pk and error_fk = 34) = 0
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 34)


@howlong
def underpay_invalid_outpatient_event(register_element):
    """
        Санкции на неверно оформленные услуги по поликлинике с заболеванием
    """
    old_query = """
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
                LEFT join provided_service_sanction pss
                    on pss.service_fk = provided_service.id_pk and pss.error_fk = 34
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
    """

    query = """
        select ps.id_pk
        from
            (
                select provided_event.id_pk as event_id,
                    count(case when ms.reason_fk = 1 and provided_service.tariff > 0 then 1 else null end) as on_disease_primary,
                    count(case when ms.reason_fk = 1 and provided_service.tariff = 0 then 1 else null end) as on_disease_secondary,
                    count(case when ms.reason_fk = 2 and provided_service.tariff > 0 then 1 else null end) as on_prevention,
                    count(case when ms.reason_fk = 5 and provided_service.tariff > 0 then 1 else null end) as on_emergency
                from
                    provided_service
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
                    and provided_event.term_fk = 3
                    --and department.level <> 3
                    and ms.reason_fk in (1, 2, 5) and (ms.group_fk not in (19, 27)
                        or ms.group_fk is NUll)
                group by provided_event.id_pk
            ) as T
            JOIN provided_service ps
                on ps.event_fk = T.event_id
        WHERE
            NOT (
                (on_disease_primary = 1 and on_disease_secondary > 0 and on_prevention = 0 and on_emergency = 0)
                or (on_disease_primary = 1 and on_disease_secondary = 0 and on_prevention = 0 and on_emergency = 0)
                or (on_disease_primary = 0 and on_disease_secondary = 0 and on_prevention = 1 and on_emergency = 0)
                or (on_disease_primary = 0 and on_disease_secondary = 0 and on_prevention = 0 and on_emergency = 1)
            )
            and (select count(1) from provided_service_sanction where service_fk = ps.id_pk
                 and error_fk = 34) = 0
    """
    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 34)


@howlong
def underpay_outpatient_event(register_element):
    """
        Санкции на случаи, если хоть одна услуга снята с оплаты
    """
    query = """
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
                                  and pssi.is_active
                                  and pssi.error_fk <> 70
                            ORDER BY mei.weight DESC
                            limit 1
                        )
                where mr1.is_active
                    and mr1.year = %s
                    and mr1.period = %s
                    and mr1.organization_code = %s
                    AND (medical_service.group_fk != 27 or medical_service.group_fk is NULL)
                    and ps1.payment_type_fk = 3
            ) as T
            on provided_service.event_fk = T.event_id
        LEFT JOIN provided_service_sanction pss
            on pss.service_fk = provided_service.id_pk
                and pss.error_fk = T.error_code AND pss.is_active
        where (ms.group_fk != 27 or ms.group_fk is NULL)
        and pss.id_pk is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    errors = [(rec.pk, 1, rec.accepted_payment, rec.error_code) for rec in list(services)]
    errors_pk = [rec[0] for rec in errors]

    ProvidedService.objects.filter(pk__in=errors_pk).update(
        accepted_payment=0, payment_type=3)

    with transaction.atomic():
        for rec in errors:
            set_sanction(ProvidedService.objects.get(pk=rec[0]), rec[3])


@howlong
def underpay_invalid_hitech_service_diseases(register_element):
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
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 77
        where
            mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s
            and hskd.id_pk is null
            and mr.type = 2
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
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 78
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

    #set_sanctions(services1, 77)
    set_sanctions(services2, 78)


@howlong
def underpay_wrong_age_adult_examination(register_element):
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
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 35
        where ms.group_fk IN (7, 25, 26)
            and substr(pe.comment, 5, 1) = '0'
            and (extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk and tariff > 0)) - EXTRACT(YEAR FROM p.birthdate)) not in (
                select DISTINCT age from adult_examination_service
            )
            and mr.is_active
            and mr.year = %s
            and mr.period = %s
            and mr.organization_code = %s)
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 35)


@howlong
def underpay_adult_examination_service_count(register_element):
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

    set_sanctions(services1, 34)
    set_sanctions(services2, 34)


@howlong
def underpay_ill_formed_children_examination(register_element):
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

    set_sanctions(services, 34)


@howlong
def underpay_wrong_examination_attachment(register_element):
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
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 1
        WHERE mr1.is_active
            and mr1.year = %s
            and mr1.period = %s
            and mr1.organization_code = %s
            and mr1.organization_code != medOrg.code
            and pss.id_pk is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 1)


@howlong
def underpay_wrong_age_examination_children_adopted(register_element):
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
            LEFT join provided_service_sanction pss
                on pss.service_fk = ps.id_pk and pss.error_fk = 35
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
            ) and pss.id_pk is null
    """

    services = ProvidedService.objects.raw(
        query, [register_element['year'], register_element['period'],
                register_element['organization_code']])

    set_sanctions(services, 35)


@howlong
def underpay_wrong_age_examination_children_difficult(register_element):
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


@howlong
def underpay_wrong_gender_examination(register_element):
    """
    Санкции на несоответствие услуги полу
    """
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
                 and (ms.examination_primary or ms.examination_final)
                 and ms.is_cost
                 and pt.gender_fk <> ms.gender_fk
                 and ps.payment_type_fk = 2
            """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    return set_sanctions(services, 41)


@howlong
def underpay_duplicate_examination_in_current_register(register_element):
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

    set_sanctions(services, 64)


@howlong
def underpay_service_term_kind_mismatch(register_element):
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

    set_sanctions(services, 79)


@howlong
def underpay_service_term_mismatch(register_element):
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

    set_sanctions(services, 76)


@howlong
def underpay_second_phase_examination(register_element):
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

    set_sanctions(services, 34)


@howlong
def underpay_neurologist_first_phase_exam(register_element):
    query = """
            select ps2.id_pk
            FROM provided_service ps2
            where ps2.event_fk in (
                select DISTINCT ps1.event_fk
                from (
                    select pe.id_pk AS event_id
                    FROM medical_register mr
                        JOIN medical_register_record mrr
                           ON mr.id_pk = mrr.register_fk
                        JOIN provided_event pe
                           ON mrr.id_pk = pe.record_fk
                        JOIN provided_service ps
                           ON ps.event_fk = pe.id_pk
                        JOIN medical_service ms
                           ON ms.id_pk = ps.code_fk
                    WHERE mr.is_active
                       AND mr.period = %(period)s
                       AND mr.year = %(year)s
                       AND mr.organization_code = %(organization)s
                       AND ps.payment_type_fk = 2
                       AND ms.code = '019001'
                       AND ps.start_date >= '2015-04-01'
                 ) as T
                 JOIN provided_service ps1
                    ON ps1.event_fk = T.event_id
                 JOIN medical_service ms1
                    ON ms1.id_pk = ps1.code_fk
                 where
                     ms1.code = '019020'
                     and ps1.start_date <= '2015-04-01'
                     AND ps1.payment_type_fk = 2)
            """
    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 78)


@howlong
def underpay_multi_division_disease_events(register_element):
    query = """
        SELECT DISTINCT ps.id_pk
        from (
            select
            pe.id_pk AS event_id
            from medical_register mr JOIN medical_register_record mrr
                ON mr.id_pk=mrr.register_fk
            JOIN provided_event pe
                ON mrr.id_pk=pe.record_fk
            JOIN provided_service ps
                ON ps.event_fk=pe.id_pk
            JOIN medical_service ms
                ON ms.id_pk = ps.code_fk
            where mr.is_active and mr.year = %(year)s
                and mr.period = %(period)s
                AND mr.organization_code = %(organization)s
                AND (ms.group_fk not in (27, 19) or ms.group_fk is null)
                AND ps.payment_type_fk = 2
                AND pe.term_fk = 3
            group by event_id
            HAVING count(distinct ms.division_fk) > 1
            ) AS T
            join provided_service ps
                 ON ps.event_fk = T.event_id
        where (select count(*) from provided_service_sanction where error_fk = 78 and service_fk = ps.id_pk) = 0
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 78)


@howlong
def underpay_multi_subgrouped_stomatology_events(register_element):
    query = """
            select provided_service.id_pk from provided_service join (
                select
                    pe.id_pk, count(distinct ps.id_pk) as count_services
                from medical_register mr JOIN medical_register_record mrr
                    ON mr.id_pk=mrr.register_fk
                JOIN provided_event pe
                    ON mrr.id_pk=pe.record_fk
                JOIN provided_service ps
                    ON ps.event_fk=pe.id_pk
                JOIN medical_organization mo
                    ON mo.id_pk = ps.organization_fk
                join patient pt
                    on pt.id_pk = mrr.patient_fk
                JOIN medical_service ms
                    ON ms.id_pk = ps.code_fk
                where mr.is_active and mr.year = %(year)s
                    and mr.period = %(period)s
                    and ms.group_fk = 19
                    and ps.payment_type_fk = 2
                    and ms.subgroup_fk is not null
                    and mr.organization_code = %(organization)s
                group by 1
                order by 2
            ) as T on T.id_pk = event_fk
            and T.count_services > 1
            where (select count(*) from provided_service_sanction
                where service_fk = provided_service.id_pk and error_fk = 78) = 0
            """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 78)

@howlong
def underpay_hitech_with_small_duration(register_element):
    query = """
        select ps.id_pk from (
        select ps.event_fk as event_id, ps.tariff, ps.quantity, ps.end_date - ps.start_date, ms.code, ps.end_date,
            COALESCE(
                (
                    select "value"
                    from hitech_service_nkd
                    where start_date = (select max(start_date) from hitech_service_nkd where start_date <= ps.end_date)
                        and vmp_group = ms.vmp_group
                    order by start_date DESC
                    limit 1
                ), 1
            ) as nkd,
            ms.vmp_group,
            ms.tariff_profile_fk

        from provided_service ps
            join provided_event pe
                on ps.event_fk = pe.id_pk
            join medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            JOIN medical_organization department
                on department.id_pk = ps.department_fk
        where
            mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and mr.type = 2) as T
            JOIN provided_service ps
                on ps.event_fk = T.event_id
        WHERE T.quantity / T.nkd * 100 < 40
            --and (select count(*) from provided_service_sanction
            --     where service_fk = ps.id_pk and error_fk = 78) = 0


    """
    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 78)

@howlong
def underpay_incorrect_examination_events(register_element):
    query = """
        select ps.id_pk from (
        select event_id, total, required, required_interview, required_therapy, round(total/greatest(required, 1)::NUMERIC * 100, 0) as service_percentage, extra
        from (
            select pe.id_pk event_id,
                (
                    select count(
                        case
                        when aes.service_fk = 8355 and aes.age < 36 and aes.gender_fk = 1 then NULL
                        when aes.service_fk = 8355 and aes.age < 45 and aes.gender_fk = 2 THEN NULL
                        ELSE 1
                        END
                    )
                    from provided_service
                        join examination_tariff aes
                            on aes.gender_fk = p.gender_fk
                                and aes.service_fk = provided_service.code_fk
                                and aes.age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                                and mo.regional_coefficient = aes.regional_coefficient
                                and aes.start_date =
                                    GREATEST(
                                        (select max(start_date)
                                         from examination_tariff
                                         where start_date <= pe.end_date
                                         and service_fk = ps.code_fk),
                                         '2015-06-01'
                                    )
                    WHERE provided_service.event_fk = pe.id_pk
                ) total,
                (
                    select count(
                        case
                        when examination_tariff.service_fk = 8355 and examination_tariff.age < 36 and examination_tariff.gender_fk = 1 then NULL
                        when examination_tariff.service_fk = 8355 and examination_tariff.age < 45 and examination_tariff.gender_fk = 2 THEN NULL
                        ELSE 1
                        END
                    )
                    from examination_tariff
                    where gender_fk = p.gender_fk
                        and age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                        and mo.regional_coefficient = regional_coefficient
                        and start_date =
                            GREATEST(
                                (select max(start_date)
                                 from examination_tariff
                                 where start_date <= pe.end_date
                                 and service_fk = ps.code_fk),
                                 '2015-06-01'
                            )
                ) required,
                (
                    select count(provided_service.id_pk)
                    from provided_service
                        LEFT join examination_tariff aes
                            on aes.gender_fk = p.gender_fk
                                and aes.service_fk = provided_service.code_fk
                                and aes.age = extract(YEAR from (select max(end_date) from provided_service where event_fk = pe.id_pk)) - EXTRACT(YEAR FROM p.birthdate)
                                and mo.regional_coefficient = aes.regional_coefficient
                                and aes.start_date =
                                    GREATEST(
                                        (select max(start_date)
                                         from examination_tariff
                                         where start_date <= pe.end_date
                                         and service_fk = ps.code_fk),
                                         '2015-06-01'
                                    )
                    WHERE provided_service.event_fk = pe.id_pk and provided_service.code_fk <> 8339
                        and aes.id_pk is null
                        and provided_service.tariff > 0
                ) extra,
                sum(case when ms.code in ('019002') THEN 1 ELSE 0 END) as required_interview,
                sum(case when ms.code in ('019021', '019023', '019022', '019024') THEN 1 ELSE 0 END) as required_therapy
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
                join medical_organization mo
                    on mo.parent_fk is null and mo.code = mr.organization_code
            WHERE
                mr.is_active
                and mr.year = %(year)s
                and mr.period = %(period)s
                and mr.organization_code = %(organization)s
                and ms.group_fk = 7
                and ms.code <> '019001'
                and pe.end_date >= '2015-06-01'
            GROUP BY 1, 2, 3, 4
        ) as T) as T2
        join provided_service ps
            on ps.event_fk = T2.event_id
        WHERE (service_percentage < 85 or required_interview <> 1 or required_therapy <> 1 or extra > 0)
            and (select count(1) from provided_service_sanction where error_fk = 78 and service_fk = ps.id_pk) = 0
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 78)

@howlong
def underpay_old_examination_services(register_element):
    query = """
        select ps.id_pk
        from provided_service ps
            join provided_event pe
                on pe.id_pk = ps.event_fk
            JOIN medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            JOIN medical_register mr
                on mr.id_pk = mrr.register_fk
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk

        WHERE mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s

            and ms.code not in ('019001')
            and ps.end_date < (select end_date from provided_service where event_fk = pe.id_pk and code_fk = 8347)
            and mr.type = 3
            and (select count(1) from provided_service_sanction where service_fk = ps.id_pk and error_fk = 70) = 0
            and pe.end_date > '2015-06-01'
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    for service in services:
        service.payment_type_id = 3
        service.accepted_payment = 0
        service.calculated_payment = 0
        service.save()

        sanction = Sanction.objects.create(
            type_id=1, service=service,
            underpayment=service.invoiced_payment,
            is_active=True,
            error_id=70)

        SanctionStatus.objects.create(
            sanction=sanction,
            type=SanctionStatus.SANCTION_TYPE_ADDED_BY_MEK)

@howlong
def underpay_incorrect_preventive_examination_event(register_element):
    query = """
        select ps.id_pk
        from
            (
                select pe.id_pk event_id,
                    count(case when ps.code_fk in (10771, 10772) then 1 else NULL END) as "first",
                    count(case when ps.code_fk in (10773, 10774) then 1 else NULL END) as "last"

                from provided_service ps
                    join provided_event pe
                        on pe.id_pk = ps.event_fk
                    JOIN medical_register_record mrr
                        on mrr.id_pk = pe.record_fk
                    JOIN medical_register mr
                        on mr.id_pk = mrr.register_fk
                    JOIN patient p
                        on p.id_pk = mrr.patient_fk
                    JOIN medical_organization dep
                        on dep.id_pk = ps.department_fk
                    JOIN medical_Service ms
                        on ms.id_pk = ps.code_fk
                WHERE mr.is_active
                    and mr.year = %(year)s
                    and mr.period = %(period)s
                    and mr.organization_code = %(organization)s
                    and ps.payment_type_fk = 2
                    --and mr.status_fk > 4
                    and ms.group_fk = 9
                group by pe.id_pk
            ) as T
            join provided_service ps
                on ps.event_fk = T.event_id

        where T.first <> 1 or T.last <> 1
            and (select count(1) from provided_service_sanction where service_fk = ps.id_pk and error_fk = 34) = 0
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 34)

@howlong
def underpay_repeated_preventive_examination_event(register_element):
    query = """
        select DISTINCT id_pk from (
        select
            DISTINCT
            ps.event_fk as event_id,
            row_number() over (PARTITION BY i.id, ms.code order by pe.end_date, pe.id_pk, ms.code) as rnum_repeated,
            p.last_name, p.first_name, p.middle_name
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
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
        where mr.is_active
            and mr.organization_code = %(organization)s
            and mr.year = %(year)s
            and mr.period = %(period)s
            and ms.group_fk = 11
            and ps.payment_type_fk = 2
            and ps.tariff > 0
            and ms.code in ('119084',
                '119085',
                '119086',
                '119087',
                '119088',
                '119089',
                '119090',
                '119091'
            )
        ) as T
            join provided_service
                on event_fk = event_id
        where rnum_repeated > 1
            and (select count(1) from provided_service_sanction where service_fk = provided_service.id_pk and error_fk = 67) = 0
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 67)

@howlong
def underpay_services_at_weekends(register_element):
    query = """
        select
            ps.id_pk
        from
            provided_service ps
            join provided_event pe
                on pe.id_pk = ps.event_fk
            join medical_register_record mrr
                on mrr.id_pk = pe.record_fk
            join medical_register mr
                on mrr.register_fk = mr.id_pk
            JOIN medical_service ms
                on ms.id_pk = ps.code_fk
            join medical_organization mo
                on mo.code = mr.organization_code
                    and mo.parent_fk is null
        WHERE mr.is_active
            and mr.year = %(year)s
            and mr.period = %(period)s
            and mr.organization_code = %(organization)s
            and (
                (pe.term_fk = 3 and (ms.reason_fk != 5 or ms.reason_fk is null)
                    and extract(DOW FROM ps.start_date) = 0 and (ms.group_fk <> 31 or ms.group_fk is NULL))
                or (pe.term_fk in (1, 2) and (extract(DOW FROM ps.end_date) = 6
                    or extract(DOW FROM ps.start_date) IN (6, 0)) and (ms.group_fk <> 31 or ms.group_fk is NULL))
            )
    """

    services = ProvidedService.objects.raw(
        query, dict(year=register_element['year'],
                    period=register_element['period'],
                    organization=register_element['organization_code']))

    set_sanctions(services, 52)
