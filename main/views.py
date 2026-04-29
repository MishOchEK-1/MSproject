from django.shortcuts import render

def index(request):
    return render(
        request,
        'main/index.html',
        {
            'project_name': 'Maker Space',
            'modules': [
                'Пользователи и роли',
                'Оборудование и категории',
                'Бронирование и подтверждение',
                'Уведомления и журнал действий',
            ],
        },
    )
