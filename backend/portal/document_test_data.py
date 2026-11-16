"""Fictional document data shared by workflow and concurrent request tests."""
PERSON = {
    'first_name': 'Иван', 'last_name': 'Тестов', 'patronymic': 'Вымышленный',
    'birth_date': '2000-01-02', 'phone': '+79990000000',
    'passport_series': '0000', 'passport_number': '000001', 'passport_issued_by': 'Вымышленный отдел тестовых документов',
    'passport_issued_on': '2020-01-02', 'passport_department_code': '000-000',
    'registration_address': 'Тестовая область, вымышленный город, улица Проверочная, дом 1, квартира 2',
    'residential_address': 'Тестовая область, вымышленный город, улица Проверочная, дом 3, квартира 4',
    'snils': '000-000-000 00', 'inn': '123456789012', 'institution': 'Вымышленный колледж',
    'education_level': 'studying',
}
PROGRAM = {'program_kind': 'повышения квалификации', 'study_form': '1'}
REGISTRATION = {'sequence': 321, 'number_code': 'О', 'realization_year': '26/28', 'department': '1',
                'contract_date': '2026-01-21', 'university_representative': 'Тестовый Представитель, директор',
                'authority_basis': 'тестовой доверенности № 1', 'university_email': 'test@example.invalid'}
