#! -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from django.db import connection
from medical_service_register.path import REESTR_EXP, BASE_DIR
from helpers.excel_writer import ExcelWriter
from helpers.excel_style import VALUE_STYLE, PERIOD_VALUE_STYLE
from helpers.const import MONTH_NAME, ACT_CELL_POSITION
import time


### Структура для актов дневного стационара
def get_day_hospital_structure():
    day_hospital_query = """
         SELECT medical_register.organization_code,
         COUNT(DISTINCT (patient.id_pk, medical_division.term_fk,
               medical_service.group_fk, medical_service.tariff_profile_fk)) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN (patient.id_pk, medical_division.term_fk, medical_service.group_fk,
                     medical_service.tariff_profile_fk) END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN (patient.id_pk, medical_division.term_fk,
                     medical_service.group_fk, medical_service.tariff_profile_fk) END) AS children_population,

         COUNT(DISTINCT provided_service.id_pk) AS all_hospitaliztion,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN provided_service.id_pk END) AS adult_hospitalization,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN provided_service.id_pk END) AS children_hospitalization,

         SUM(round(provided_service.quantity, 2)) AS all_quantity,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN round(provided_service.quantity, 2) ELSE 0 END) AS adult_quantity,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN round(provided_service.quantity, 2) ELSE 0 END) AS children_quantity,

         SUM(round(provided_service.accepted_payment, 2)) AS all_accepted_payment,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN round(provided_service.accepted_payment, 2) ELSE 0 END) AS adult_accepted_payment,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN round(provided_service.accepted_payment, 2) ELSE 0 END) AS children_accepted_payment

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
             JOIN medical_division
                 ON medical_division.id_pk = provided_service.division_fk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND provided_service.payment_type_fk in (2, 4)
             AND ({condition})
         GROUP BY medical_register.organization_code
         """

    return [{'title': u'Дневной стационар',
             'pattern': 'day_hospital',
             'sum': [
                 {'query': (day_hospital_query,
                            """
                            (provided_event.term_fk=2 and
                             medical_division.term_fk in (10, 11) and
                             medical_service.group_fk is null)
                             or medical_service.group_fk in (17, 28)
                            """),
                  'cell_count': 12,
                  'separator_length': 2},
                 {'query': (day_hospital_query,
                            """
                            provided_event.term_fk=2 and
                            medical_service.group_fk = 28
                            """),
                  'cell_count': 12,
                  'separator_length': 2}
             ]},
            {'title': u'Дневной стационар на дому',
             'pattern': 'day_hospital_home',
             'sum': [
                 {'query': (day_hospital_query,
                            """
                            provided_event.term_fk=2 and
                            medical_division.term_fk=12 and
                            medical_service.group_fk is null
                            """),
                  'cell_count': 12,
                  'separator_length': 2}
             ]},
            {'title': u'Дневной стационар свод',
             'pattern': 'day_hospital_all',
             'sum': [
                 {'query': (day_hospital_query,
                            """
                            (provided_event.term_fk=2 and medical_service.group_fk is null)
                             or medical_service.group_fk in (17, 28)
                            """),
                  'cell_count': 12,
                  'separator_length': 2}
             ]}]


### Структура актов по стоматологии
def get_stomatology_structure():
    stomatology_disease_query = """
         SELECT medical_register.organization_code,

         COUNT(DISTINCT patient.id_pk) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN patient.id_pk END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN patient.id_pk END) AS adult_population,

         COUNT(DISTINCT provided_service.event_fk) AS all_treatment,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN provided_service.event_fk END) AS adult_treatment,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN provided_service.event_fk END) AS adult_treatment,

         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL
               THEN provided_service.id_pk END) AS all_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '0%'
               THEN provided_service.id_pk END) AS adult_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '1%'
               THEN provided_service.id_pk END) AS children_receiving,

         SUM(provided_service.quantity*medical_service.uet) AS all_uet,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS adult_uet,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS children_uet,

         SUM(provided_service.accepted_payment) AS all_payment,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.accepted_payment ELSE 0 END) AS adult_payment,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.accepted_payment ELSE 0 END) AS children_payment

         FROM provided_service
         JOIN medical_service
             ON provided_service.code_fk = medical_service.id_pk
         JOIN provided_event
             ON provided_service.event_fk = provided_event.id_pk
         JOIN medical_register_record
             ON provided_event.record_fk = medical_register_record.id_pk
         JOIN patient
             ON patient.id_pk = medical_register_record.patient_fk
         JOIN medical_register
             ON medical_register_record.register_fk = medical_register.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND (medical_service.group_fk = 19
                  AND EXISTS (
                         SELECT 1
                         FROM provided_service ps2
                         JOIN medical_service ms2
                             ON ps2.code_fk = ms2.id_pk
                         JOIN provided_event pe2
                             ON (pe2.id_pk = ps2.event_fk
                                 AND pe2.id_pk = provided_event.id_pk
                                 AND provided_service.end_date = ps2.end_date
                                 AND provided_service.start_date = ps2.start_date)
                         WHERE ms2.subgroup_fk in ({condition})
                               AND ps2.payment_type_fk = 2
                        )
                 )
             AND provided_service.payment_type_fk = 2
         GROUP BY medical_register.organization_code
         """

    stomatology_proph_or_ambulance_query = """
         SELECT medical_register.organization_code,

         COUNT(DISTINCT patient.id_pk) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN patient.id_pk END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
              THEN patient.id_pk END) AS adult_population,

         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL
              THEN provided_service.id_pk END) AS all_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '0%'
              THEN provided_service.id_pk END) AS adult_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '1%'
              THEN provided_service.id_pk END) AS children_receiving,

         SUM(provided_service.quantity*medical_service.uet) AS all_uet,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS adult_uet,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS children_uet,

         SUM(provided_service.accepted_payment) AS all_payment,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.accepted_payment ELSE 0 END) AS adult_payment,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.accepted_payment ELSE 0 END) AS children_payment

         FROM provided_service
         JOIN medical_service
             ON provided_service.code_fk = medical_service.id_pk
         JOIN provided_event
             ON provided_service.event_fk = provided_event.id_pk
         JOIN medical_register_record
             ON provided_event.record_fk = medical_register_record.id_pk
         JOIN patient
             ON patient.id_pk = medical_register_record.patient_fk
         JOIN medical_register
             ON medical_register_record.register_fk = medical_register.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND (medical_service.group_fk = 19
                  AND EXISTS (
                         SELECT 1
                         FROM provided_service ps2
                         JOIN medical_service ms2
                             ON ps2.code_fk = ms2.id_pk
                         JOIN provided_event pe2
                             ON (pe2.id_pk = ps2.event_fk
                                 AND pe2.id_pk = provided_event.id_pk
                                 AND provided_service.end_date = ps2.end_date
                                 AND provided_service.start_date = ps2.start_date
                                 )
                         WHERE ms2.subgroup_fk in ({condition})
                             AND ps2.payment_type_fk = 2
                        )
                 )
             AND provided_service.payment_type_fk = 2
         GROUP BY medical_register.organization_code
         """

    stomatology_emergency_query = """
         SELECT medical_register.organization_code,

         COUNT(DISTINCT patient.id_pk) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN patient.id_pk END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN patient.id_pk END) AS adult_population,

         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL
               THEN provided_service.id_pk END) AS all_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '0%'
               THEN provided_service.id_pk END) AS adult_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '1%'
               THEN provided_service.id_pk END) AS children_receiving,

         SUM(provided_service.quantity*medical_service.uet) AS all_uet,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS adult_uet,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS children_uet,

         SUM(provided_service.tariff) AS all_tariff,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.tariff ELSE 0 END) AS adult_tariff,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.tariff ELSE 0 END) AS children_tariff,

         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=4
             THEN round(provided_service.tariff*0.2, 2) ELSE 0 END) AS all_emergency,
         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=4 AND medical_service.code like '0%'
             THEN round(provided_service.tariff*0.2, 2) ELSE 0 END) AS adult_emergency,
         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=4 AND medical_service.code like '1%'
             THEN round(provided_service.tariff*0.2, 2) ELSE 0 END) AS children_emergency,

         SUM(provided_service.accepted_payment) AS all_payment,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.accepted_payment ELSE 0 END) AS adult_payment,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.accepted_payment ELSE 0 END) AS children_payment

         FROM provided_service
         JOIN medical_service
             ON provided_service.code_fk = medical_service.id_pk
         JOIN provided_event
             ON provided_service.event_fk = provided_event.id_pk
         JOIN medical_register_record
             ON provided_event.record_fk = medical_register_record.id_pk
         JOIN patient
             ON patient.id_pk = medical_register_record.patient_fk
         JOIN medical_register
             ON medical_register_record.register_fk = medical_register.id_pk
         LEFT JOIN provided_service_coefficient
             ON provided_service_coefficient.service_fk=provided_service.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND (medical_service.group_fk = 19
                     AND EXISTS (
                         SELECT 1
                         FROM provided_service ps2
                         JOIN medical_service ms2
                             ON ps2.code_fk = ms2.id_pk
                         JOIN provided_event pe2
                             ON (pe2.id_pk = ps2.event_fk
                                 AND pe2.id_pk = provided_event.id_pk
                                 AND provided_service.end_date = ps2.end_date
                                 AND provided_service.start_date = ps2.start_date
                                 )
                         WHERE ms2.subgroup_fk in ({condition})
                             AND ps2.payment_type_fk = 2
                        )
                 )
             AND provided_service.payment_type_fk = 2
         GROUP BY medical_register.organization_code
         """

    stomatology_total_query = """
         SELECT medical_register.organization_code,

         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL
               THEN (patient.id_pk, medical_service.subgroup_fk) END) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '0%'
               THEN (patient.id_pk, medical_service.subgroup_fk) END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '1%'
               THEN (patient.id_pk, medical_service.subgroup_fk) END) AS adult_population,

         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk=12
               THEN provided_service.event_fk END) AS all_treatment,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk=12 AND medical_service.code like '0%'
               THEN provided_service.event_fk END) AS adult_treatment,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk=12 AND medical_service.code like '1%'
               THEN provided_service.event_fk END) AS adult_treatment,

         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL
               THEN provided_service.id_pk END) AS all_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '0%'
               THEN provided_service.id_pk END) AS adult_receiving,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NOT NULL AND medical_service.code like '1%'
               THEN provided_service.id_pk END) AS children_receiving,

         SUM(provided_service.quantity*medical_service.uet) AS all_uet,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS adult_uet,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.quantity*medical_service.uet ELSE 0 END) AS children_uet,

         SUM(provided_service.tariff) AS all_tariff,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.tariff ELSE 0 END) AS adult_tariff,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.tariff ELSE 0 END) AS children_tariff,

         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=4
             THEN round(provided_service.tariff*0.2, 2) ELSE 0 END) AS all_emergency,
         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=4 AND medical_service.code like '0%'
             THEN round(provided_service.tariff*0.2, 2) ELSE 0 END) AS adult_emergency,
         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=4 AND medical_service.code like '1%'
             THEN round(provided_service.tariff*0.2, 2) ELSE 0 END) AS children_emergency,

         SUM(provided_service.accepted_payment) AS all_payment,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.accepted_payment ELSE 0 END) AS adult_payment,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.accepted_payment ELSE 0 END) AS children_payment

         FROM provided_service
         JOIN medical_service
             ON provided_service.code_fk = medical_service.id_pk
         JOIN provided_event
             ON provided_service.event_fk = provided_event.id_pk
         JOIN medical_register_record
             ON provided_event.record_fk = medical_register_record.id_pk
         JOIN patient
             ON patient.id_pk = medical_register_record.patient_fk
         JOIN medical_register
             ON medical_register_record.register_fk = medical_register.id_pk
         LEFT JOIN provided_service_coefficient
             ON provided_service_coefficient.service_fk=provided_service.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND (medical_service.group_fk = 19
                  AND EXISTS (
                         SELECT 1
                         FROM provided_service ps2
                         JOIN medical_service ms2
                             ON ps2.code_fk = ms2.id_pk
                         JOIN provided_event pe2
                             ON (pe2.id_pk = ps2.event_fk
                                 AND pe2.id_pk = provided_event.id_pk
                                 AND provided_service.end_date = ps2.end_date
                                 AND provided_service.start_date = ps2.start_date
                                 )
                         WHERE ms2.subgroup_fk in ({condition})
                             AND ps2.payment_type_fk = 2
                        )
                 )
              AND provided_service.payment_type_fk = 2
         GROUP BY medical_register.organization_code
         """

    return [{'title': u'Стоматология',
             'pattern': 'stomatology',
             'sum': [
                 {'query': (stomatology_disease_query, '12'),
                  'cell_count': 15,
                  'separator_length': 0},
                 {'query': (stomatology_proph_or_ambulance_query, '13'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (stomatology_proph_or_ambulance_query, '14'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (stomatology_emergency_query, '17'),
                  'cell_count': 18,
                  'separator_length': 0},
                 {'query': (stomatology_total_query, '12, 13, 14, 17'),
                  'cell_count': 21,
                  'separator_length': 0}]},
            ]


### Структура актов для круглосуточного стационара
def get_hospital_structure():
    hospital_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT (patient.id_pk, medical_service.group_fk,
                         medical_service.tariff_profile_fk)) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN (patient.id_pk, medical_service.group_fk,
                     medical_service.tariff_profile_fk) END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN (patient.id_pk, medical_service.group_fk,
                     medical_service.tariff_profile_fk) END) AS children_population,

         COUNT(DISTINCT CASE WHEN (medical_service.group_fk IS NULL OR medical_service.group_fk in (1, 2, 20))
               THEN provided_service.id_pk END) AS all_hospitalization,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               AND (medical_service.group_fk IS NULL OR medical_service.group_fk in (1, 2, 20))
               THEN provided_service.id_pk END) AS adult_hospitalization,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               AND (medical_service.group_fk IS NULL OR medical_service.group_fk in (1, 2, 20))
               THEN provided_service.id_pk END) AS children_hospitalization,

         SUM(CASE WHEN (medical_service.group_fk IS NULL OR medical_service.group_fk in (1, 2, 20))
             THEN round(provided_service.quantity, 2) ELSE 0 END) AS all_quantity,
         SUM(CASE WHEN medical_service.code like '0%'
             AND (medical_service.group_fk IS NULL OR medical_service.group_fk in (1, 2, 20))
             THEN round(provided_service.quantity, 2) ELSE 0 END) AS adult_quantity,
         SUM(CASE WHEN medical_service.code like '1%'
             AND (medical_service.group_fk IS NULL OR medical_service.group_fk in (1, 2, 20))
             THEN round(provided_service.quantity, 2) ELSE 0 END) AS children_quantity,

         SUM(provided_service.accepted_payment) AS all_accepted_payment,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.accepted_payment ELSE 0 END) AS adult_accepted_payment,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.accepted_payment ELSE 0 END) AS children_accepted_payment
         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND provided_service.payment_type_fk in (2, 4)
             AND ({condition})
         GROUP BY medical_register.organization_code
         """

    hospital_total_query = """
         SELECT
         medical_register.organization_code,
         SUM(round(provided_service.tariff, 2)) AS all_tariff,

         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=2
             THEN provided_service.tariff*0.015 ELSE 0 END) all_caf_coef,

         -SUM(CASE WHEN provided_service_coefficient.coefficient_fk=6
             THEN round(provided_service.tariff*0.7, 2) ELSE 0 END) all_exc_vol,

         SUM(provided_service.accepted_payment) AS all_accepted_payment
         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
             LEFT JOIN provided_service_coefficient
                 ON provided_service_coefficient.service_fk = provided_service.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND provided_service.payment_type_fk in (2, 4)
             AND ({condition})
         GROUP BY medical_register.organization_code
         """

    hospital_hmc_query = """
         SELECT
         DISTINCT medical_register.organization_code,
         COUNT(DISTINCT (patient.id_pk, medical_service.tariff_profile_fk)) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN (patient.id_pk, medical_service.tariff_profile_fk) END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN (patient.id_pk, medical_service.tariff_profile_fk) END) AS children_population,

         COUNT(provided_service.id_pk) AS all_hospitalization,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN provided_service.id_pk END) AS adult_hospitalization,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN provided_service.id_pk END) AS children_hospitalization,

         SUM(round(provided_service.quantity, 2)) AS all_quantity,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN round(provided_service.quantity, 2) ELSE 0 END) AS adult_quantity,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN round(provided_service.quantity, 2) ELSE 0 END) AS children_quantity,

         SUM(provided_service.accepted_payment) AS all_accepted_payment,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.accepted_payment ELSE 0 END) AS adult_accepted_payment,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.accepted_payment ELSE 0 END) AS children_accepted_payment

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND provided_service.payment_type_fk in (2, 4)
             AND medical_service.group_fk = 20
             AND medical_service.tariff_profile_fk in ({condition})
         GROUP BY medical_register.organization_code
         """

    hospital_hmc_total_query = """
         SELECT
         medical_register.organization_code, SUM(provided_service.tariff) AS all_tariff
         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
         WHERE medical_register.is_active
             AND medical_register.year = '{year}'
             AND medical_register.period = '{period}'
             AND provided_service.payment_type_fk in (2, 4)
             AND medical_service.group_fk = 20
             AND medical_service.tariff_profile_fk in ({condition})
         GROUP BY medical_register.organization_code
         """

    return [{'title': u'Круглосуточный стационар',
             'pattern': 'hospital',
             'sum': [
                 {'query': (hospital_query,
                            """
                            (provided_event.term_fk = 1 AND medical_service.group_fk IS NULL)
                            OR medical_service.group_fk in (1, 2, 3)
                            """),
                  'cell_count': 12,
                  'separator_length': 2},
                 {'query': (hospital_total_query,
                            """
                            (provided_event.term_fk = 1 AND
                            medical_service.group_fk IS NULL)
                            OR medical_service.group_fk in (1, 2, 3)
                            """),
                  'cell_count': 4,
                  'separator_length': 2}]},
            {'title': u'Круглосуточный стационар ВМП',
             'pattern': 'hospital_hmc',
             'sum': [
                 {'query': (hospital_hmc_query, '56'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '57'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '58'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '59'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '60'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '63'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '61'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '62'),
                  'cell_count': 12,
                  'separator_length': 0},
                 {'query': (hospital_hmc_query, '56, 57, 58, 59, 60, 63, 61, 62'),
                  'cell_count': 12,
                  'separator_length': 2},
                 {'query': (hospital_hmc_total_query, '56, 57, 58, 59, 60, 63, 61, 62'),
                  'cell_count': 1,
                  'separator_length': 0}]},
            {'title': u'Круглосуточный стационар свод',
             'pattern': 'hospital_all',
             'sum': [{
                 'query': (hospital_query,
                           """
                           (provided_event.term_fk = 1 AND medical_service.group_fk IS NULL)
                           OR medical_service.group_fk in (1, 2, 3, 20)
                           """),
                 'cell_count': 12,
                 'separator_length': 0
             }]}]


### Структура актов по скорой помощи
def get_acute_care_structure():
    acute_care_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT (patient.id_pk, medical_service.division_fk)) AS all_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN (patient.id_pk, medical_service.division_fk) END) AS adult_population,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN (patient.id_pk, medical_service.division_fk) END) AS children_population,

         COUNT(DISTINCT provided_service.id_pk) AS all_hospitalization,
         COUNT(DISTINCT CASE WHEN medical_service.code like '0%'
               THEN provided_service.id_pk END) AS adult_hospitalization,
         COUNT(DISTINCT CASE WHEN medical_service.code like '1%'
               THEN provided_service.id_pk END) AS children_hospitalization,

         SUM(provided_service.tariff) AS all_tariff,
         SUM(CASE WHEN medical_service.code like '0%'
             THEN provided_service.tariff ELSE 0 END) AS adult_tariff,
         SUM(CASE WHEN medical_service.code like '1%'
             THEN provided_service.tariff ELSE 0 END) AS children_tariff

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
         WHERE medical_register.is_active
               AND medical_register.year = '{year}'
               AND medical_register.period = '{period}'
               AND provided_service.payment_type_fk in (2, 4)
               AND provided_event.term_fk = 4
               AND medical_service.division_fk in ({condition})
         GROUP BY medical_register.organization_code
         """

    return [{'title': u'СМП финансирование по подушевому нормативу (кол-во, основной тариф)',
             'pattern': 'acute_care',
             'sum': [
                 {'query': (acute_care_query, '456'),
                  'cell_count': 9,
                  'separator_length': 0},
                 {'query': (acute_care_query, '455'),
                  'cell_count': 9,
                  'separator_length': 0},
                 {'query': (acute_care_query, '457'),
                  'cell_count': 9,
                  'separator_length': 0},
                 {'query': (acute_care_query, '458'),
                  'cell_count': 9,
                  'separator_length': 0},
                 {'query': (acute_care_query, '456, 455, 457, 458'),
                  'cell_count': 9,
                  'separator_length': 0}]}]


### Структура актов периодических медосмотров
def get_periodic_med_exam_structure():
    periodic_med_exam_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT patient.id_pk) AS all_population,

         COUNT(DISTINCT provided_service.id_pk) AS all_hospitalization,

         SUM(provided_service.tariff) AS all_tariff,

         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=5
             THEN round(provided_service.tariff*1.07, 2) ELSE 0 END),

         SUM(provided_service.accepted_payment) AS all_accepted_payment

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
             LEFT JOIN provided_service_coefficient ON provided_service_coefficient.id_pk =
                 (SELECT provided_service_coefficient.id_pk
                  FROM provided_service_coefficient
                  WHERE provided_service.id_pk = provided_service_coefficient.service_fk LIMIT 1)

         WHERE medical_register.is_active
               AND medical_register.year = '{year}'
               AND medical_register.period = '{period}'
               AND provided_service.payment_type_fk in (2, 4)
               AND medical_service.group_fk=16 and medical_service.subgroup_fk is NULL
               {condition}
         GROUP BY medical_register.organization_code
         """

    return [{'title': u'Периодический медицинский осмотр несовершеннолетних',
             'pattern': 'periodic_medical_examination',
             'sum': [
                 {'query': (periodic_med_exam_query, ''),
                  'cell_count': 5,
                  'separator_length': 0}]}]


### Структура актов предварительных медосмотров
def get_preliminary_med_exam_structure():
    preliminary_med_exam_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NULL
               THEN (patient.id_pk, medical_service.id_pk) END) AS all_population,

         COUNT(DISTINCT provided_service.id_pk) AS all_hospitalization,

         SUM(provided_service.tariff) AS all_tariff,

         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=5
             THEN round(provided_service.tariff*1.07, 2) ELSE 0 END),

         SUM(provided_service.accepted_payment) AS all_accepted_payment

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
             LEFT JOIN provided_service_coefficient
                 ON provided_service_coefficient.id_pk =
                 (SELECT provided_service_coefficient.id_pk
                  FROM provided_service_coefficient
                  WHERE provided_service.id_pk = provided_service_coefficient.service_fk
                  LIMIT 1)

         WHERE medical_register.is_active
               AND medical_register.year = '{year}'
               AND medical_register.period = '{period}'
               AND provided_service.payment_type_fk in (2, 4)
               AND {condition}
         GROUP BY medical_register.organization_code
         """

    preliminary_med_exam_spec_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT patient.id_pk) AS all_population,

         COUNT(DISTINCT provided_service.id_pk) AS all_hospitalization

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk

         WHERE medical_register.is_active
               AND medical_register.year = '{year}'
               AND medical_register.period = '{period}'
               AND provided_service.payment_type_fk in (2, 4)
               AND {condition}
         GROUP BY medical_register.organization_code
         """

    return [{'title': u'Предварительный медицинский осмотр несовершеннолетних',
             'pattern': 'preliminary_medical_examination',
             'sum': [
                 {'query': (preliminary_med_exam_query, "medical_service.code='119101'"),
                  'cell_count': 5,
                  'separator_length': 0},
                 {'query': (preliminary_med_exam_query, "medical_service.code='119119'"),
                  'cell_count': 5,
                  'separator_length': 0},
                 {'query': (preliminary_med_exam_query, "medical_service.code='119120'"),
                  'cell_count': 5,
                  'separator_length': 0},
                 {'query': (preliminary_med_exam_query,
                            """
                            medical_service.code in
                            ('119101', '119119', '119120')
                            """),
                  'cell_count': 5,
                  'separator_length': 1},
                 {'query': (preliminary_med_exam_spec_query,
                            """
                            medical_service.group_fk=15 and
                            medical_service.subgroup_fk=11
                            """),
                  'cell_count': 2,
                  'separator_length': 2},
                 {'query': (preliminary_med_exam_query,
                            """
                            medical_service.group_fk=15 and
                            (medical_service.subgroup_fk=11
                              or medical_service.code in ('119101', '119119', '119120'))
                            """),
                  'cell_count': 5,
                  'separator_length': 0}
             ]}]


### Структура актов профиактических осмотров
def get_preventive_med_exam_structure():
    preventive_med_exam_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 2 AND medical_service.subgroup_fk IS NULL
               THEN (patient.id_pk, medical_service.id_pk) END) AS all_female_population,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 1 AND medical_service.subgroup_fk IS NULL
               THEN (patient.id_pk, medical_service.id_pk) END) AS all_male_population,

         COUNT(DISTINCT CASE WHEN patient.gender_fk = 2
               THEN provided_service.id_pk END) AS all_female_hospitalization,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 1
               THEN provided_service.id_pk END) AS all_male_hospitalization,

         SUM(CASE WHEN patient.gender_fk = 2
             THEN provided_service.tariff ELSE 0 END) AS all_female_tariff,
         SUM(CASE WHEN patient.gender_fk = 1
             THEN provided_service.tariff ELSE 0 END) AS all_male_tariff,


         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=5 AND patient.gender_fk = 2
             THEN round(provided_service.tariff*1.07, 2) ELSE 0 END) AS all_female_coeff,
         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=5 AND patient.gender_fk = 1
             THEN round(provided_service.tariff*1.07, 2) ELSE 0 END) AS all_male_coeff,

         SUM(CASE WHEN patient.gender_fk = 2
             THEN provided_service.accepted_payment ELSE 0 END) AS all_female_accepted_payment,
         SUM(CASE WHEN patient.gender_fk = 1
             THEN provided_service.accepted_payment ELSE 0 END) AS all_male_accepted_payment

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
             LEFT JOIN provided_service_coefficient
                 ON provided_service_coefficient.id_pk =
                 (SELECT provided_service_coefficient.id_pk
                  FROM provided_service_coefficient
                  WHERE provided_service.id_pk = provided_service_coefficient.service_fk
                  LIMIT 1)

         WHERE medical_register.is_active
               AND medical_register.year = '{year}'
               AND medical_register.period = '{period}'
               AND provided_service.payment_type_fk in (2, 4)
               AND ({condition})
         GROUP BY medical_register.organization_code
         """

    preventive_med_exam_total_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT CASE WHEN medical_service.subgroup_fk IS NULL
               THEN (patient.id_pk, medical_service.id_pk) END) AS all_population,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 2 AND medical_service.subgroup_fk IS NULL
               THEN (patient.id_pk, medical_service.id_pk) END) AS all_female_population,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 1 AND medical_service.subgroup_fk IS NULL
               THEN (patient.id_pk, medical_service.id_pk) END) AS all_male_population,

         COUNT(DISTINCT provided_service.id_pk) AS all_hospitalization,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 2
               THEN provided_service.id_pk END) AS all_female_hospitalization,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 1
               THEN provided_service.id_pk END) AS all_male_hospitalization,

         SUM(provided_service.tariff) AS all_tariff,
         SUM(CASE WHEN patient.gender_fk = 2
             THEN provided_service.tariff ELSE 0 END) AS all_female_tariff,
         SUM(CASE WHEN patient.gender_fk = 1
             THEN provided_service.tariff ELSE 0 END) AS all_male_tariff,

         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=5
             THEN round(provided_service.tariff*1.07, 2) ELSE 0 END) AS all_coeff,
         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=5 and patient.gender_fk = 2
             THEN round(provided_service.tariff*1.07, 2) ELSE 0 END) AS all_female_coeff,
         SUM(CASE WHEN provided_service_coefficient.coefficient_fk=5 and patient.gender_fk = 1
             THEN round(provided_service.tariff*1.07, 2) ELSE 0 END) AS all_male_coeff,

         SUM(provided_service.accepted_payment) AS all_accepted_payment,
         SUM(CASE WHEN patient.gender_fk = 2
             THEN provided_service.accepted_payment ELSE 0 END) AS all_female_accepted_payment,
         SUM(CASE WHEN patient.gender_fk = 1
             THEN provided_service.accepted_payment ELSE 0 END) AS all_male_accepted_payment

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk
             LEFT JOIN provided_service_coefficient
                 ON provided_service_coefficient.id_pk =
                 (SELECT provided_service_coefficient.id_pk
                  FROM provided_service_coefficient
                  WHERE provided_service.id_pk = provided_service_coefficient.service_fk
                  LIMIT 1)

         WHERE medical_register.is_active
               AND medical_register.year = '{year}'
               AND medical_register.period = '{period}'
               AND provided_service.payment_type_fk in (2, 4)
               AND ({condition})
         GROUP BY medical_register.organization_code
         """

    preventive_med_exam_spec_query = """
         SELECT
         medical_register.organization_code,
         COUNT(DISTINCT patient.id_pk) AS all_population,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 2
               THEN patient.id_pk END) AS all_female_population,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 1
               THEN patient.id_pk END) AS all_male_population,

         COUNT(DISTINCT provided_service.id_pk) AS all_hospitalization,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 2
               THEN provided_service.id_pk END) AS all_female_hospitalization,
         COUNT(DISTINCT CASE WHEN patient.gender_fk = 1
               THEN provided_service.id_pk END) AS all_male_hospitalization

         FROM provided_service
             JOIN medical_service
                 ON medical_service.id_pk = provided_service.code_fk
             JOIN provided_event
                 ON provided_service.event_fk = provided_event.id_pk
             JOIN medical_register_record
                 ON provided_event.record_fk = medical_register_record.id_pk
             JOIN medical_register
                 ON medical_register_record.register_fk = medical_register.id_pk
             JOIN patient
                 ON medical_register_record.patient_fk = patient.id_pk

         WHERE medical_register.is_active
               AND medical_register.year = '{year}'
               AND medical_register.period = '{period}'
               AND provided_service.payment_type_fk in (2, 4)
               AND (medical_service.group_fk=11 AND medical_service.subgroup_fk=8)
               {condition}
         GROUP BY medical_register.organization_code
         """

    return [{'title': u'Профилактический медицинский осмотр несовершеннолетних',
             'pattern': 'preventive_medical_examination',
             'sum': [
                 {'query': (preventive_med_exam_query,
                            """
                            medical_service.code in ('119051', '119080', '119081')
                            """),
                  'cell_count': 10,
                  'separator_length': 0},
                 {'query': (preventive_med_exam_query,
                            """
                            medical_service.code in ('119052', '119082', '119083')
                            """),
                  'cell_count': 10,
                  'separator_length': 0},
                 {'query': (preventive_med_exam_query,
                            """
                            medical_service.code in ('119053', '119084', '119085')
                            """),
                  'cell_count': 10,
                  'separator_length': 0},
                 {'query': (preventive_med_exam_query,
                            """
                            medical_service.code in ('119054', '119086', '119087')
                            """),
                  'cell_count': 10,
                  'separator_length': 0},
                 {'query': (preventive_med_exam_query,
                            """
                            medical_service.code in ('119055', '119088', '119089')
                            """),
                  'cell_count': 10,
                  'separator_length': 0},
                 {'query': (preventive_med_exam_query,
                            """
                            medical_service.code in ('119056', '119090', '119091')
                            """),
                  'cell_count': 10,
                  'separator_length': 0},
                 {'query': (preventive_med_exam_total_query,
                            """
                            medical_service.code in ('119051', '119052', '119053',
                                                     '119054', '119055', '119056',
                                                     '119080', '119081', '119082',
                                                     '119083', '119084', '119085',
                                                     '119086', '119087', '119088',
                                                     '119089', '119090', '119091')
                            """),
                  'cell_count': 15,
                  'separator_length': 2},
                 {'query': (preventive_med_exam_spec_query, ''),
                  'cell_count': 6,
                  'separator_length': 2},
                 {'query': (preventive_med_exam_total_query,
                            """
                            medical_service.group_fk=11 AND
                            (medical_service.subgroup_fk=8
                            OR medical_service.code in ('119051', '119052', '119053',
                                                        '119054', '119055', '119056',
                                                        '119080', '119081', '119082',
                                                        '119083', '119084', '119085',
                                                        '119086', '119087', '119088',
                                                        '119089', '119090', '119091')
                            )
                            """),
                  'cell_count': 15,
                  'separator_length': 0},

             ]}]


class Command(BaseCommand):

    def handle(self, *args, **options):
        year = args[0]
        period = args[1]
        target_dir = REESTR_EXP % (year, period)
        act_path_t = ur'{dir}\{title}_{month}_{year}'
        temp_path_t = ur'{base}\templates\excel_pattern\end_of_month\{template}.xls'
        start = time.clock()
        query_cursor = connection.cursor()

        acts_structure = [
            get_day_hospital_structure(),
            get_stomatology_structure(),
            get_hospital_structure(),
            get_acute_care_structure(),
            get_periodic_med_exam_structure(),
            get_preliminary_med_exam_structure(),
            get_preventive_med_exam_structure()
        ]

        for structure in acts_structure:

            for rule in structure:
                print rule['title']
                act_path = act_path_t.format(dir=target_dir,
                                             title=rule['title'],
                                             month=MONTH_NAME[period],
                                             year=year)
                temp_path = temp_path_t.format(base=BASE_DIR,
                                               template=rule['pattern'])
                print temp_path

                with ExcelWriter(act_path, template=temp_path,
                                 sheet_names=[MONTH_NAME[period], ]) \
                        as act_book:
                    act_book.set_overall_style({'font_size': 11, 'border': 1})
                    act_book.set_cursor(4, 2)
                    act_book.set_style(PERIOD_VALUE_STYLE)
                    act_book.write_cell(u'за %s %s года' % (MONTH_NAME[period], year))
                    act_book.set_style(VALUE_STYLE)
                    block_index = 2
                    for condition in rule['sum']:
                        total_sum = []
                        query_cursor.execute(
                            condition['query'][0].format(
                                year=year, period=period,
                                condition=condition['query'][1]))

                        for mo_data in query_cursor.fetchall():
                            if not total_sum:
                                total_sum = [0, ]*condition['cell_count']
                            act_book.set_cursor(ACT_CELL_POSITION[mo_data[0]], block_index)

                            for index, cell_value in enumerate(mo_data[1:]):
                                total_sum[index] += cell_value
                                act_book.write_cell(cell_value, 'c')

                        act_book.set_cursor(101, block_index)
                        for cell_value in total_sum:
                            act_book.write_cell(cell_value, 'c')

                        block_index += condition['cell_count'] + \
                            condition['separator_length']
        query_cursor.close()
        elapsed = time.clock() - start
        print u'Время выполнения: {0:d} мин {1:d} сек'.format(int(elapsed//60), int(elapsed % 60))
