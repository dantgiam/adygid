

(function () {
  "use strict";
  const OFFERS = [{"id": "rafting-1", "cat": "adventure", "sub": "rafting", "title": "Короткий сплав по горной реке", "area": "Даховская", "price": 2800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "raft", "blurb": "Короткий участок для первого знакомства с водой. В этом демо маршрут и ограничения вымышлены."}, {"id": "rafting-2", "cat": "adventure", "sub": "rafting", "title": "Сплав семейным темпом", "area": "Даховская", "price": 3500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": true, "photo": "raft", "blurb": "Спокойный темп, остановки на берегу. Подходит ли детям — в боевой версии уточнял бы организатор; здесь это только макет."}, {"id": "rafting-3", "cat": "adventure", "sub": "rafting", "title": "Полный день на воде", "area": "Хамышки", "price": 4500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 день", "familyAsk": false, "photo": "raft", "blurb": "Длинный день на реке. Состав группы и сезон в демо не подтверждены."}, {"id": "kayak-1", "cat": "adventure", "sub": "kayak_sup", "title": "Прогулка на каяке по спокойному участку", "area": "Гузерипль", "price": 2200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": false, "photo": "kayak", "blurb": "Каяк на тихой воде. Опыт и снаряжение в макете не оговариваются."}, {"id": "kayak-2", "cat": "adventure", "sub": "kayak_sup", "title": "Утро на сапборде", "area": "Каменномостский", "price": 1800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1,5 часа", "familyAsk": true, "photo": "sup", "blurb": "Сапборд на открытой воде. Погода и место старта в демо условные."}, {"id": "canyon-1", "cat": "adventure", "sub": "canyoning", "title": "Спуск вдоль ручья с проводником", "area": "Хамышки", "price": 4200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "4 часа", "familyAsk": false, "photo": "canyon", "blurb": "Каньонинг: вода, страховка, спуски. Требования к участникам в макете не выдуманы до конца — только визуал."}, {"id": "canyon-2", "cat": "adventure", "sub": "canyoning", "title": "Короткое знакомство с каньоном", "area": "Даховская", "price": 3300, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": false, "photo": "canyon", "blurb": "Более короткий выход. Оборудование и допуск уточнялись бы с организатором."}, {"id": "extreme-1", "cat": "adventure", "sub": "extreme_park", "title": "Верёвочный парк, два маршрута", "area": "Каменномостский", "price": 1900, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "park", "blurb": "Троллеи и верёвочные трассы. Возрастные рамки в демо не утверждаются."}, {"id": "extreme-2", "cat": "adventure", "sub": "extreme_park", "title": "Виа-феррата коротким кругом", "area": "Хаджох", "price": 3100, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": false, "photo": "ferrata", "blurb": "Страховочный трос на скале. Это иллюстрация формата, не конкретная трасса."}, {"id": "cave-1", "cat": "adventure", "sub": "caving", "title": "Экскурсия в пещеру с гидом", "area": "Лаго-Наки", "price": 900, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "cave", "blurb": "Оборудованная пещера. Часы работы и цена в демо вымышлены."}, {"id": "cave-2", "cat": "adventure", "sub": "caving", "title": "Расширенный спелеомаршрут", "area": "Лаго-Наки", "price": 2400, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": false, "photo": "cave", "blurb": "Более длинный подземный выход. Допуск и снаряжение в макете не подтверждены."}, {"id": "climb-1", "cat": "adventure", "sub": "climbing", "title": "Скалолазание с инструктором, два часа", "area": "Хаджох", "price": 2700, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": false, "photo": "climb", "blurb": "Занятия на скале. Уровень подготовки в демо не проверяется."}, {"id": "climb-2", "cat": "adventure", "sub": "climbing", "title": "День на маршрутах с связкой", "area": "Гузерипль", "price": 3900, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "полдня", "familyAsk": false, "photo": "climb", "blurb": "Несколько трасс за полдня. Условия — только для наглядности макета."}, {"id": "jeep", "cat": "offroad", "sub": "jeeping", "title": "Джиппинг по горным маршрутам", "area": "Даховская и Каменномостский", "price": 5000, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "полдня", "familyAsk": false, "photo": "jeep2", "blurb": "Канонический пример расчёта: 5 000 ₽ за группу. Маршрут в демо условный."}, {"id": "jeeping-2", "cat": "offroad", "sub": "jeeping", "title": "Вечерний выезд на смотровые", "area": "Даховская", "price": 6500, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "3 часа", "familyAsk": false, "photo": "jeep2", "blurb": "Короче по времени, с закатным светом. Точки остановок вымышлены."}, {"id": "jeeping-3", "cat": "offroad", "sub": "jeeping", "title": "День на плато на внедорожнике", "area": "Лаго-Наки", "price": 11000, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "1 день", "familyAsk": false, "photo": "jeep2", "blurb": "Длинный день в горах. Доступ на плато в боевой версии зависел бы от сезона и режима, здесь это не обещание."}, {"id": "quad-1", "cat": "offroad", "sub": "quad", "title": "Прокат квадроцикла, короткий круг", "area": "Каменномостский", "price": 3500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": false, "photo": "atv", "blurb": "Один круг по грунтовке. Требования к управлению в демо не расписаны."}, {"id": "quad-2", "cat": "offroad", "sub": "quad", "title": "Квадроциклы, маршрут на полдня", "area": "Хаджох", "price": 8000, "unit": "group", "unitLabel": "пример расчёта за маршрут", "duration": "полдня", "familyAsk": false, "photo": "atv", "blurb": "Групповой выезд. Цена — пример за маршрут, не за человека."}, {"id": "enduro-1", "cat": "offroad", "sub": "enduro", "title": "Эндуро-сопровождение, два часа", "area": "Хамышки", "price": 4500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": false, "photo": "enduro", "blurb": "Мотоцикл и сопровождение. Опыт вождения в макете не проверяется."}, {"id": "enduro-2", "cat": "offroad", "sub": "enduro", "title": "День по лесным дорогам", "area": "Гузерипль", "price": 9000, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 день", "familyAsk": false, "photo": "enduro", "blurb": "Длинный выезд. Маршрут и техника вымышлены."}, {"id": "snow-1", "cat": "offroad", "sub": "snowmobile", "title": "Прогулка на снегоходе", "area": "Лаго-Наки", "price": 4000, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "snowmobile", "blurb": "Короткий зимний выезд. Сезон и трасса в демо условные."}, {"id": "snow-2", "cat": "offroad", "sub": "snowmobile", "title": "Снегоходный маршрут на полдня", "area": "Лаго-Наки", "price": 7500, "unit": "group", "unitLabel": "пример расчёта за маршрут", "duration": "полдня", "familyAsk": false, "photo": "snowmobile", "blurb": "Длиннее и для группы. Наличие снега здесь не обещается."}, {"id": "hike-1", "cat": "guides", "sub": "hiking_guide", "title": "Пеший выход с гидом на полдня", "area": "Каменномостский", "price": 2500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "4 часа", "familyAsk": true, "photo": "hike", "blurb": "Тропа и рассказ по дороге. Темп в демо не зафиксирован."}, {"id": "hike-2", "cat": "guides", "sub": "hiking_guide", "title": "Ранний подъём к смотровой", "area": "Гузерипль", "price": 3200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "5 часов", "familyAsk": false, "photo": "hike", "blurb": "Ранее утро, набор высоты. Сложность указана только для вида карточки."}, {"id": "exc-1", "cat": "guides", "sub": "excursion", "title": "Обзорная экскурсия на день", "area": "Каменномостский и Даховская", "price": 4000, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 день", "familyAsk": true, "photo": "hikers", "blurb": "Несколько точек за день. Программа собрана для макета, не как готовый тур."}, {"id": "exc-2", "cat": "guides", "sub": "excursion", "title": "Короткий выезд по долине", "area": "Хаджох", "price": 2800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "5 часов", "familyAsk": true, "photo": "road", "blurb": "Меньше точек, спокойнее график."}, {"id": "exc-3", "cat": "guides", "sub": "excursion", "title": "Знакомство с Майкопом и окрестностями", "area": "Майкоп", "price": 3300, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "полдня", "familyAsk": true, "photo": "cafe", "blurb": "Город и ближние остановки. Маршрут вымышлен."}, {"id": "multi-1", "cat": "guides", "sub": "multiday_tour", "title": "Поход на два дня с ночёвкой", "area": "Гузерипль", "price": 8900, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 дня", "familyAsk": false, "photo": "camp", "blurb": "Ночёвка в полевых условиях. Состав лагеря в демо не утверждён."}, {"id": "multi-2", "cat": "guides", "sub": "multiday_tour", "title": "Трёхдневный кольцевой выход", "area": "Лаго-Наки", "price": 14500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 дня", "familyAsk": false, "photo": "hike", "blurb": "Длинный формат. Доступ и погода не обещаются."}, {"id": "winter-1", "cat": "guides", "sub": "winter_guide", "title": "Зимняя прогулка на снегоступах", "area": "Лаго-Наки", "price": 2700, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": true, "photo": "snowshoe", "blurb": "Короткий зимний выход. Наличие снега в макете не подтверждено."}, {"id": "winter-2", "cat": "guides", "sub": "winter_guide", "title": "Зимний день с гидом", "area": "Лаго-Наки", "price": 4800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 день", "familyAsk": false, "photo": "snowshoe", "blurb": "Длиннее, с запасом по времени на погоду."}, {"id": "family-1", "cat": "guides", "sub": "family_program", "title": "День в горах с детьми", "area": "Каменномостский", "price": 3600, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "полдня", "familyAsk": true, "photo": "hikers", "blurb": "Короткие отрезки и запас на отдых. Возраст в демо не задан жёстко."}, {"id": "family-2", "cat": "guides", "sub": "family_program", "title": "Игровая прогулка у реки", "area": "Хаджох", "price": 2400, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "hikers", "blurb": "Совсем короткий формат для семей."}, {"id": "museum-1", "cat": "guides", "sub": "museum_ethno", "title": "Этнографическая экскурсия", "area": "Майкоп", "price": 1200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "museum", "blurb": "Музей или этнокомплекс. Часы работы вымышлены."}, {"id": "museum-2", "cat": "guides", "sub": "museum_ethno", "title": "Семейный визит в этнокомплекс", "area": "Каменномостский", "price": 1500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": true, "photo": "museum", "blurb": "Чуть длиннее, с запасом на мастер-зону — только как идея макета."}, {"id": "master-1", "cat": "guides", "sub": "masterclass", "title": "Мастер-класс по керамике", "area": "Майкоп", "price": 2200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "pottery", "blurb": "Гончарный круг и обжиг по договорённости. Это не студия конкретного мастера."}, {"id": "master-2", "cat": "guides", "sub": "masterclass", "title": "Кухонный мастер-класс", "area": "Даховская", "price": 2600, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": true, "photo": "khachapuri", "blurb": "Готовите блюдо вместе с ведущим. Рецепт и площадка в демо условные."}, {"id": "photo-1", "cat": "guides", "sub": "photo", "title": "Фотопрогулка на рассвете", "area": "Лаго-Наки", "price": 5000, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "2 часа", "familyAsk": false, "photo": "photographer", "blurb": "Съёмка на свету. Результат и локации не обещаны — только вид карточки."}, {"id": "photo-2", "cat": "guides", "sub": "photo", "title": "Семейная съёмка в долине", "area": "Даховская", "price": 4500, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "1,5 часа", "familyAsk": true, "photo": "photographer", "blurb": "Короткий слот для семьи. Это не портфолио конкретного фотографа."}, {"id": "horse-1", "cat": "animals_farms", "sub": "horse", "title": "Конная прогулка, час", "area": "Каменномостский", "price": 2000, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "horse", "blurb": "Короткий выход верхом. Подбор лошади в демо не описан."}, {"id": "horse-2", "cat": "animals_farms", "sub": "horse", "title": "Полудневный конный маршрут", "area": "Хаджох", "price": 3800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "4 часа", "familyAsk": false, "photo": "horse", "blurb": "Длиннее, с остановкой. Опыт всадника в макете не проверяется."}, {"id": "horse-3", "cat": "animals_farms", "sub": "horse", "title": "Вечерняя прогулка в седле", "area": "Даховская", "price": 2500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1,5 часа", "familyAsk": true, "photo": "horse", "blurb": "Короткий вечерний формат."}, {"id": "husky-1", "cat": "animals_farms", "sub": "husky", "title": "Знакомство с хаски", "area": "Лаго-Наки", "price": 1800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "husky", "blurb": "Короткий визит к собакам. Сезон и площадка условные."}, {"id": "husky-2", "cat": "animals_farms", "sub": "husky", "title": "Катание в упряжке", "area": "Лаго-Наки", "price": 3500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "30 минут", "familyAsk": true, "photo": "husky", "blurb": "Короткая трасса. Снег и доступность не обещаются."}, {"id": "alpaca-1", "cat": "animals_farms", "sub": "petting_zoo", "title": "Визит к альпакам и ламам", "area": "Майкоп", "price": 900, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "alpaca", "blurb": "Контактный визит. Это не конкретная ферма, только иллюстрация."}, {"id": "alpaca-2", "cat": "animals_farms", "sub": "petting_zoo", "title": "Семейный час в контактном зоопарке", "area": "Каменномостский", "price": 1200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1,5 часа", "familyAsk": true, "photo": "alpaca", "blurb": "Чуть дольше, с детьми. Правила общения с животными в демо не расписаны."}, {"id": "trout-1", "cat": "animals_farms", "sub": "trout", "title": "Прогулка по форелевому хозяйству", "area": "Хамышки", "price": 700, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "trout", "blurb": "Посмотреть пруды и кормление. Не обещание рыбалки."}, {"id": "trout-2", "cat": "animals_farms", "sub": "trout", "title": "Рыбалка на хозяйстве, полдня", "area": "Хамышки", "price": 2500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "полдня", "familyAsk": false, "photo": "trout", "blurb": "Формат «попробовать поймать». Правила и вылов в макете не заданы."}, {"id": "apiary-1", "cat": "animals_farms", "sub": "apiary", "title": "Экскурсия на пасеку", "area": "Даховская", "price": 800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "bees", "blurb": "Рассказ про ульи и дегустация мёда — как идея карточки."}, {"id": "apiary-2", "cat": "animals_farms", "sub": "apiary", "title": "Дегустация мёда с прогулкой", "area": "Новопрохладное", "price": 1100, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1,5 часа", "familyAsk": true, "photo": "bees", "blurb": "Чуть шире по времени. Сорта и объёмы вымышлены."}, {"id": "farm-1", "cat": "animals_farms", "sub": "farm_visit", "title": "Утро на ферме", "area": "Каменномостский", "price": 1500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "goats", "blurb": "Прогулка по хозяйству. Это не объявление конкретного двора."}, {"id": "farm-2", "cat": "animals_farms", "sub": "farm_visit", "title": "Семейный день на ферме", "area": "Майкоп", "price": 2300, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "4 часа", "familyAsk": true, "photo": "goats", "blurb": "Длиннее, с запасом на обед — только как макет."}, {"id": "cafe-1", "cat": "food", "sub": "cafe", "title": "Обед на террасе с видом", "area": "Даховская", "price": 1600, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1,5 часа", "familyAsk": true, "photo": "cafe", "blurb": "Посадка в кафе. Меню и столики в демо вымышлены."}, {"id": "cafe-2", "cat": "food", "sub": "cafe", "title": "Завтрак перед выездом в горы", "area": "Каменномостский", "price": 900, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "cafe", "blurb": "Короткий утренний слот."}, {"id": "cuisine-1", "cat": "food", "sub": "adyghe_cuisine", "title": "Гастроужин с кавказскими блюдами", "area": "Майкоп", "price": 3200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": false, "photo": "shashlik", "blurb": "Ужин как впечатление. Блюда на фото — иллюстрация типа кухни, не меню конкретного ресторана Адыгеи."}, {"id": "cuisine-2", "cat": "food", "sub": "adyghe_cuisine", "title": "Семейный обед национальной кухни", "area": "Хаджох", "price": 2400, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "khachapuri", "blurb": "Дневной формат. Фото еды иллюстративное."}, {"id": "cheese-1", "cat": "food", "sub": "cheese", "title": "Дегустация сыров", "area": "Каменномостский", "price": 1500, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1 час", "familyAsk": true, "photo": "cheese", "blurb": "Несколько сортов и рассказ. Это не карточка конкретной сыроварни."}, {"id": "cheese-2", "cat": "food", "sub": "cheese", "title": "Сыр и чай с прогулкой", "area": "Даховская", "price": 1900, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "1,5 часа", "familyAsk": true, "photo": "cheese", "blurb": "Чуть длиннее дегустация."}, {"id": "wine-1", "cat": "food", "sub": "winery", "title": "Дегустация на винодельне", "area": "Майкоп", "price": 2100, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": false, "photo": "wine", "blurb": "Короткая дегустация. Возрастные ограничения в боевой версии были бы обязательны; здесь это макет."}, {"id": "wine-2", "cat": "food", "sub": "winery", "title": "Винодельня с прогулкой по участку", "area": "Майкоп", "price": 2800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": false, "photo": "wine", "blurb": "Длиннее, с прогулкой. Локация условная."}, {"id": "shop-1", "cat": "food", "sub": "farm_shop", "title": "Сбор фермерского набора", "area": "Каменномостский", "price": 1800, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "40 минут", "familyAsk": true, "photo": "market", "blurb": "Набор продуктов «на вечер». Состав вымышлен, цена — пример за набор."}, {"id": "shop-2", "cat": "food", "sub": "farm_shop", "title": "Утренняя лавка: сыр, мёд, хлеб", "area": "Даховская", "price": 1200, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "30 минут", "familyAsk": true, "photo": "market", "blurb": "Короткий заход за продуктами. Не конкретная лавка."}, {"id": "glamp-1", "cat": "stay", "sub": "glamping", "title": "Ночь в глэмпинге", "area": "Даховская", "price": 8500, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "glamping", "blurb": "Шатёр или модуль на ночь. Вместимость в демо не подтверждена."}, {"id": "glamp-2", "cat": "stay", "sub": "glamping", "title": "Глэмпинг на двое суток", "area": "Лаго-Наки", "price": 8200, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "glamping", "blurb": "Та же идея, другой район. Цена — за сутки, число суток выбирается в заявке."}, {"id": "base-1", "cat": "stay", "sub": "base", "title": "Домик на базе отдыха", "area": "Каменномостский", "price": 5500, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "lodge", "blurb": "Отдельный домик. Удобства описаны не будут — только вид карточки."}, {"id": "base-2", "cat": "stay", "sub": "base", "title": "Номер на турбазе у реки", "area": "Гузерипль", "price": 4200, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "lodge", "blurb": "Проще и ближе к воде. Это не объявление конкретной базы."}, {"id": "guest-1", "cat": "stay", "sub": "guesthouse", "title": "Ночь в гостевом доме", "area": "Каменномостский", "price": 4500, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "lodge", "blurb": "Комната в гостевом доме. Адрес и хозяева вымышлены."}, {"id": "guest-2", "cat": "stay", "sub": "guesthouse", "title": "Семейный номер в доме у склона", "area": "Даховская", "price": 6200, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "lodge", "blurb": "Чуть просторнее. Без реального объекта."}, {"id": "camp-1", "cat": "stay", "sub": "camping", "title": "Место под палатку", "area": "Гузерипль", "price": 800, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "camp", "blurb": "Палаточный стан. Костёр и удобства в демо не оговорены."}, {"id": "camp-2", "cat": "stay", "sub": "camping", "title": "Автокемпинг на ночь", "area": "Хаджох", "price": 1500, "unit": "night", "unitLabel": "пример расчёта за сутки", "duration": "сутки", "familyAsk": true, "photo": "camp", "blurb": "Место под машину и палатку."}, {"id": "shelter-1", "cat": "stay", "sub": "shelter", "title": "Ночёвка в горном приюте", "area": "Лаго-Наки", "price": 2000, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "ночь", "familyAsk": false, "photo": "hut", "blurb": "Место в приюте. Режим доступа в горы не обещается."}, {"id": "shelter-2", "cat": "stay", "sub": "shelter", "title": "Приют с ужином, место в общей комнате", "area": "Лаго-Наки", "price": 2800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "ночь", "familyAsk": false, "photo": "hut", "blurb": "Чуть полный пакет. Условия вымышлены."}, {"id": "ski-1", "cat": "rental", "sub": "ski", "title": "Прокат лыж на день", "area": "Лаго-Наки", "price": 1800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "сутки", "familyAsk": false, "photo": "ski", "blurb": "Комплект на день. Размеры и наличие в демо не ведутся."}, {"id": "ski-2", "cat": "rental", "sub": "ski", "title": "Лыжи плюс час с инструктором", "area": "Лаго-Наки", "price": 3200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": true, "photo": "ski", "blurb": "Прокат и короткое занятие. Это не школа и не курорт."}, {"id": "tube-1", "cat": "rental", "sub": "tubing", "title": "Прокат ватрушки, два часа", "area": "Лаго-Наки", "price": 800, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "tube", "blurb": "Ватрушка на склоне. Склон и часы работы вымышлены."}, {"id": "tube-2", "cat": "rental", "sub": "tubing", "title": "Семейный комплект ватрушек", "area": "Лаго-Наки", "price": 2200, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "2 часа", "familyAsk": true, "photo": "tube", "blurb": "Несколько ватрушек на компанию, цена за комплект."}, {"id": "ss-1", "cat": "rental", "sub": "snowshoes", "title": "Прокат снегоступов", "area": "Лаго-Наки", "price": 700, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "полдня", "familyAsk": true, "photo": "snowshoe", "blurb": "Снегоступы и палки. Снег не обещается."}, {"id": "ss-2", "cat": "rental", "sub": "snowshoes", "title": "Снегоступы на день", "area": "Лаго-Наки", "price": 1100, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "сутки", "familyAsk": false, "photo": "snowshoe", "blurb": "Длиннее срок проката."}, {"id": "gear-1", "cat": "rental", "sub": "gear", "title": "Комплект: палатка и коврики", "area": "Каменномостский", "price": 1500, "unit": "group", "unitLabel": "пример расчёта за группу", "duration": "сутки", "familyAsk": false, "photo": "camp", "blurb": "Базовый походный набор, цена за комплект на сутки."}, {"id": "gear-2", "cat": "rental", "sub": "gear", "title": "Рюкзаки и треккинговые палки", "area": "Даховская", "price": 600, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "сутки", "familyAsk": false, "photo": "camp", "blurb": "Лёгкий прокат снаряжения."}, {"id": "bike-1", "cat": "rental", "sub": "bike", "title": "Горный велосипед на полдня", "area": "Хаджох", "price": 1400, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "полдня", "familyAsk": true, "photo": "bike", "blurb": "Велосипед без сопровождения. Маршруты в демо не размечены."}, {"id": "bike-2", "cat": "rental", "sub": "bike", "title": "Велосипед на сутки", "area": "Каменномостский", "price": 2000, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "сутки", "familyAsk": false, "photo": "bike", "blurb": "Длиннее срок, тот же формат."}, {"id": "wr-1", "cat": "rental", "sub": "water_rental", "title": "Прокат сапборда", "area": "Гузерипль", "price": 1200, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "2 часа", "familyAsk": true, "photo": "sup", "blurb": "Сапборд без гида. Место спуска условное."}, {"id": "wr-2", "cat": "rental", "sub": "water_rental", "title": "Каяк на утро", "area": "Даховская", "price": 1600, "unit": "person", "unitLabel": "пример расчёта с человека", "duration": "3 часа", "familyAsk": false, "photo": "kayak", "blurb": "Каяк в прокат. Не путать со сплавом с инструктором."}, {"id": "air-1", "cat": "transfer", "sub": "airport", "title": "Трансфер из Краснодара", "area": "Краснодар — Даховская", "price": 7000, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "3–4 часа в пути", "familyAsk": true, "photo": "minibus", "blurb": "Машина из аэропорта или с вокзала. Время в пути — оценка для макета, не расписание."}, {"id": "air-2", "cat": "transfer", "sub": "airport", "title": "Трансфер из Майкопа", "area": "Майкоп — Каменномостский", "price": 3500, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "1 час в пути", "familyAsk": true, "photo": "road", "blurb": "Короче плечо. Класс авто не обещан."}, {"id": "taxi-1", "cat": "transfer", "sub": "mountain_taxi", "title": "Такси по горным дорогам, час", "area": "Даховская", "price": 1800, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "1 час", "familyAsk": true, "photo": "road", "blurb": "Почасовой формат. Дорожные условия в демо не описываются."}, {"id": "taxi-2", "cat": "transfer", "sub": "mountain_taxi", "title": "День с водителем по долине", "area": "Каменномостский", "price": 6500, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "1 день", "familyAsk": true, "photo": "road", "blurb": "Водитель на целый день, без программы экскурсии."}, {"id": "trail-1", "cat": "transfer", "sub": "trailhead", "title": "Заброска к началу тропы", "area": "Гузерипль", "price": 2500, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "по договорённости", "familyAsk": false, "photo": "road", "blurb": "Подвезти группу к старту. Точка встречи вымышлена."}, {"id": "trail-2", "cat": "transfer", "sub": "trailhead", "title": "Встреча на финише маршрута", "area": "Хамышки", "price": 2500, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "по договорённости", "familyAsk": false, "photo": "hike", "blurb": "Забрать группу в конце дня."}, {"id": "bus-1", "cat": "transfer", "sub": "minibus", "title": "Микроавтобус для компании, день", "area": "Майкоп", "price": 9000, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "1 день", "familyAsk": true, "photo": "minibus", "blurb": "Целый день на группе. Вместимость в демо не фиксируется жёстко."}, {"id": "bus-2", "cat": "transfer", "sub": "minibus", "title": "Микроавтобус на полдня", "area": "Даховская", "price": 5500, "unit": "group", "unitLabel": "пример расчёта за машину", "duration": "полдня", "familyAsk": true, "photo": "minibus", "blurb": "Короче аренда для небольшой поездки."}];
  var TAXONOMY = [
    { code: "adventure", label: "Приключения на воде, скалах и в небе", sell: true, blurb: "Рафтинг, каньонинг, экстрим-парки, пещеры с гидом, полёты.", subs: [
      { code: "rafting", label: "Рафтинг и сплавы" },
      { code: "kayak_sup", label: "Каяк и SUP" },
      { code: "canyoning", label: "Каньонинг" },
      { code: "extreme_park", label: "Экстрим-парк: троллей, виа-феррата, дюльфер, верёвочный парк" },
      { code: "caving", label: "Пещеры и спелеотуры с гидом" },
      { code: "climbing", label: "Скалолазание и альпинизм" },
      { code: "sky", label: "Параплан и воздушный шар" }
    ]},
    { code: "offroad", label: "Джип-туры и техника", sell: true, blurb: "Внедорожники и УАЗы, квадроциклы, эндуро, снегоходы.", subs: [
      { code: "jeeping", label: "Джиппинг на внедорожниках и УАЗах" },
      { code: "quad", label: "Квадроциклы и багги" },
      { code: "enduro", label: "Эндуро и мотоциклы" },
      { code: "snowmobile", label: "Снегоходы" }
    ]},
    { code: "guides", label: "Гиды, экскурсии и культура", sell: true, blurb: "Гиды-проводники, экскурсии и туры, музеи и этнокомплексы, мастер-классы, фотосессии.", subs: [
      { code: "hiking_guide", label: "Пешие походы с гидом" },
      { code: "excursion", label: "Экскурсии на день" },
      { code: "multiday_tour", label: "Многодневные туры" },
      { code: "winter_guide", label: "Зимние выходы: снегоступы, скитур" },
      { code: "family_program", label: "Детские и семейные программы" },
      { code: "museum_ethno", label: "Музеи и этнокомплексы" },
      { code: "masterclass", label: "Мастер-классы: ремёсла, кухня, керамика" },
      { code: "photo", label: "Фотосессии и фотографы" }
    ]},
    { code: "animals_farms", label: "Животные и фермы", sell: true, blurb: "Конные прогулки, хаски, альпаки и ламы, форелевые хозяйства, пасеки.", subs: [
      { code: "horse", label: "Конные прогулки и туры" },
      { code: "husky", label: "Хаски и собачьи упряжки" },
      { code: "petting_zoo", label: "Альпаки, ламы, контактные зоопарки" },
      { code: "trout", label: "Форелевые хозяйства и рыбалка" },
      { code: "apiary", label: "Пасеки и дегустация мёда" },
      { code: "farm_visit", label: "Фермы с экскурсией" }
    ]},
    { code: "food", label: "Еда и дегустации", sell: true, blurb: "Кафе и рестораны, адыгская кухня, сыроварни, винодельни.", subs: [
      { code: "cafe", label: "Кафе и рестораны" },
      { code: "adyghe_cuisine", label: "Адыгская кухня и гастроужины" },
      { code: "cheese", label: "Сыроварни и сырные дегустации" },
      { code: "winery", label: "Винодельни и дегустации" },
      { code: "farm_shop", label: "Фермерские продукты и лавки" }
    ]},
    { code: "thermal_relax", label: "Термы и отдых", sell: false, blurb: "Раздел есть в структуре, но из каталога продаж пока убран.", subs: [
      { code: "thermal", label: "Термальные источники и бассейны" },
      { code: "banya", label: "Бани и горячие чаны" },
      { code: "spa", label: "SPA и массаж" }
    ]},
    { code: "stay", label: "Где жить", sell: true, blurb: "Глэмпинги, базы и турбазы, гостевые дома, кемпинги, приюты.", subs: [
      { code: "glamping", label: "Глэмпинги" },
      { code: "base", label: "Базы отдыха и турбазы" },
      { code: "guesthouse", label: "Гостевые дома и гостиницы" },
      { code: "camping", label: "Кемпинги и автокемпинги" },
      { code: "shelter", label: "Горные приюты" }
    ]},
    { code: "rental", label: "Прокат", sell: true, blurb: "Лыжи, ватрушки, снегоступы, снаряжение, велосипеды и SUP — один раздел «где взять».", subs: [
      { code: "ski", label: "Лыжи и сноуборды, инструктор" },
      { code: "tubing", label: "Ватрушки и санки" },
      { code: "snowshoes", label: "Снегоступы и палки" },
      { code: "gear", label: "Туристическое снаряжение: палатки, рюкзаки, кошки" },
      { code: "bike", label: "Велосипеды и электровелосипеды" },
      { code: "water_rental", label: "SUP, каяки и гидрокостюмы" }
    ]},
    { code: "transfer", label: "Трансферы и поездки", sell: true, blurb: "Аэропорт и вокзал, такси по горам, заброска к маршруту, микроавтобус для группы.", subs: [
      { code: "airport", label: "Трансфер из аэропорта и с вокзала (Краснодар, Майкоп)" },
      { code: "mountain_taxi", label: "Такси по горной Адыгее" },
      { code: "trailhead", label: "Заброска к началу маршрута и встреча на финише" },
      { code: "minibus", label: "Микроавтобус или авто с водителем для группы" }
    ]}
  ];

    var PHOTO_KEYS = ["alpaca", "atv", "bees", "bike", "cafe", "camp", "canyon", "cave", "cheese", "climb", "enduro", "ferrata", "glamping", "goats", "hike", "hikers", "horse", "husky", "hut", "jeep2", "kayak", "khachapuri", "lodge", "market", "minibus", "museum", "park", "photographer", "pottery", "raft", "road", "shashlik", "ski", "snowmobile", "snowshoe", "sup", "trout", "tube", "wine"];
  var PAGE = 12;
  var TREE_LABEL = {
    adventure: "Приключения",
    offroad: "Джип-туры и техника",
    guides: "Гиды и культура",
    animals_farms: "Животные и фермы",
    food: "Еда и дегустации",
    stay: "Где жить",
    rental: "Прокат",
    transfer: "Трансферы"
  };
  var STAGES = [
    { id: "form", label: "Заявка" },
    { id: "checking", label: "Проверка" },
    { id: "offer", label: "Предложение" },
    { id: "pay", label: "Оплата сбора" },
    { id: "done", label: "Подтверждение" }
  ];
  var STAGE_ORDER = STAGES.map(function (s) { return s.id; });
  var EXAMPLE_DATE = "5 декабря 2026";
  var MONTHS = {
    "января": 0, "янв": 0, "февраля": 1, "фев": 1, "марта": 2, "мар": 2,
    "апреля": 3, "апр": 3, "мая": 4, "май": 4, "июня": 5, "июн": 5,
    "июля": 6, "июл": 6, "августа": 7, "авг": 7, "сентября": 8, "сен": 8, "сент": 8,
    "октября": 9, "окт": 9, "ноября": 10, "ноя": 10, "нояб": 10,
    "декабря": 11, "дек": 11
  };
  var state = {
    menuMode: "sidebar", menuOpen: false, menuExpanded: "", menuStep: "sections", view: "catalog", cat: "all", sub: "", query: "", family: false,
    wishDate: "", selectedId: "jeep", party: 2, nights: 1, stage: "form",
    error: "", structure: false, shown: PAGE
  };
  function catBy(code) { for (var i = 0; i < TAXONOMY.length; i++) if (TAXONOMY[i].code === code) return TAXONOMY[i]; return null; }
  function subBy(catCode, subCode) {
    var c = catBy(catCode); if (!c) return null;
    for (var i = 0; i < c.subs.length; i++) if (c.subs[i].code === subCode) return c.subs[i];
    return null;
  }
  function offerBy(id) { for (var i = 0; i < OFFERS.length; i++) if (OFFERS[i].id === id) return OFFERS[i]; return OFFERS[0]; }
  function offerCount(cat, sub) {
    var n = 0;
    for (var i = 0; i < OFFERS.length; i++) {
      if (cat && OFFERS[i].cat !== cat) continue;
      if (sub && OFFERS[i].sub !== sub) continue;
      n++;
    }
    return n;
  }
  function sellCats() { return TAXONOMY.filter(function (c) { return c.sell; }); }
  function photoSrc(key) {
    if (PHOTO_KEYS.indexOf(key) === -1) return "";
    var base = window.ADYGID_V_PHOTO || "/assets/vpechatleniya/photos/";
    if (base.charAt(base.length - 1) !== "/") base += "/";
    var rev = window.ADYGID_V_REV || "";
    return base + key + ".webp" + (rev ? ("?v=" + encodeURIComponent(rev)) : "");
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function rub(n) { return n.toLocaleString("ru-RU") + "\u00a0\u20bd"; }
  function peopleWord(n) {
    var m = n % 100; if (m > 10 && m < 20) return "человек";
    var d = n % 10; if (d === 1) return "человек"; if (d >= 2 && d <= 4) return "человека"; return "человек";
  }
  function nightsWord(n) {
    var m = n % 100; if (m > 10 && m < 20) return "суток";
    var d = n % 10; if (d === 1) return "сутки"; return "суток";
  }
  function breakdown(offer, party, nights) {
    var people = Math.max(1, Math.min(8, party | 0));
    var n = Math.max(1, Math.min(7, nights | 0));
    var subtotal;
    if (offer.unit === "person") subtotal = offer.price * people;
    else if (offer.unit === "night") subtotal = offer.price * n;
    else subtotal = offer.price;
    var fee = Math.round(subtotal * 0.05);
    return { people: people, nights: n, subtotal: subtotal, fee: fee, discount: fee, onsite: subtotal - fee, total: subtotal };
  }
  function startOfDay(d) { var x = new Date(d.getTime()); x.setHours(0, 0, 0, 0); return x; }
  function sameDate(d, y, m, day) { return d.getFullYear() === y && d.getMonth() === m && d.getDate() === day; }
  function parseWishDate(raw) {
    var s = String(raw || "").trim().toLowerCase().replace(/\s+/g, " ");
    if (!s) return { kind: "empty" };
    var d = null, m, y, mo, day;
    m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (m) { y = +m[1]; mo = +m[2] - 1; day = +m[3]; d = new Date(y, mo, day); }
    if (!d) { m = s.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})$/); if (m) { day = +m[1]; mo = +m[2] - 1; y = +m[3]; d = new Date(y, mo, day); } }
    if (!d) {
      m = s.match(/^(\d{1,2})\s+([а-яё]+)\.?\s+(\d{4})$/);
      if (m) {
        if (MONTHS[m[2]] === undefined) return { kind: "invalid" };
        day = +m[1]; mo = MONTHS[m[2]]; y = +m[3]; d = new Date(y, mo, day);
      }
    }
    if (!d || isNaN(d.getTime()) || !sameDate(d, y, mo, day)) return { kind: "invalid" };
    if (startOfDay(d) < startOfDay(new Date())) return { kind: "past", date: d };
    return { kind: "ok", date: d };
  }
  function filteredOffers() {
    var q = state.query.trim().toLowerCase();
    return OFFERS.filter(function (o) {
      if (state.cat !== "all" && o.cat !== state.cat) return false;
      if (state.sub && o.sub !== state.sub) return false;
      if (state.family && !o.familyAsk) return false;
      if (q) {
        var cat = catBy(o.cat), sub = subBy(o.cat, o.sub);
        var hay = [o.title, o.blurb, o.area, o.duration, cat ? cat.label : "", sub ? sub.label : ""].join(" ").toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }
  function moneyBox(offer, party, nights) {
    var b = breakdown(offer, party, nights);
    var unitNote;
    if (offer.unit === "person") unitNote = "Для этой услуги пример считается с человека: " + rub(offer.price) + " × " + b.people + " = " + rub(b.subtotal) + ".";
    else if (offer.unit === "night") unitNote = "Для этой услуги пример считается за сутки: " + rub(offer.price) + " × " + b.nights + " " + nightsWord(b.nights) + " = " + rub(b.subtotal) + ".";
    else unitNote = "Для этой услуги пример считается целиком (" + escapeHtml(offer.unitLabel) + "), от числа людей сумма в демо не умножается.";
    return (
      '<div class="money"><div class="head"><h3>Пример расчёта</h3><span class="badge-ex">Пример</span></div>' +
      '<div class="row"><span>Условная стоимость услуги</span><span>' + rub(b.subtotal) + '</span></div>' +
      '<div class="row"><span>Сервисный сбор АдыГиду (5%)</span><span>' + rub(b.fee) + '</span></div>' +
      '<div class="row"><span>Скидка организатора</span><span>−' + rub(b.discount) + '</span></div>' +
      '<div class="row"><span>Организатору на месте</span><span>' + rub(b.onsite) + '</span></div>' +
      '<div class="row total"><span>Всего за поездку</span><span>' + rub(b.total) + '</span></div>' +
      '<p class="note">Вы оплачиваете ' + rub(b.fee) + ' АдыГиду после согласования заявки, а ' + rub(b.onsite) +
      ' — организатору на месте. Общая сумма — ' + rub(b.total) +
      '. Сбор — плата АдыГиду за помощь с организацией, не предоплата организатору.</p>' +
      '<p class="note">' + unitNote + ' Сумма ориентировочная и вымышленная: партнёр её не подтверждал.</p></div>'
    );
  }
  function logo() {
    return '<svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><polygon points="4,24 12,10 20,24" fill="#9BCBA4"/><polygon points="10,24 21,8 30,24" fill="#278C3E"/><circle cx="24" cy="9" r="2.6" fill="#D6A324"/></svg>';
  }
  var catalogY = 0, catalogFocusId = "", detailStack = [];
  function menuIcon(code) {
    var paths = {
      all: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
      adventure: '<path d="m3 17 6-12 5 9 3-6 4 9M3 21c3-3 5 2 8 0s5-2 10 0"/>',
      offroad: '<path d="M3 16V9h12l5 5v4H3m4-9 1-4h6l1 4M15 9v5h5"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
      guides: '<circle cx="12" cy="12" r="9"/><path d="m16 8-2 6-6 2 2-6 6-2Z"/>',
      animals_farms: '<path d="M6 17c0-3 3-7 6-7s6 4 6 7c0 4-4 2-6 2s-6 2-6-2Z"/><ellipse cx="5" cy="8" rx="2" ry="3"/><ellipse cx="11" cy="5" rx="2" ry="3"/><ellipse cx="18" cy="7" rx="2" ry="3"/>',
      food: '<path d="M5 3v6c0 3 6 3 6 0V3M8 3v18M20 21V3c-5 2-5 9 0 9"/>',
      stay: '<path d="m3 11 9-8 9 8M5 10v11h14V10M9 21v-8h6v8"/>',
      rental: '<path d="m6 7 3-4h6l3 4 2 13H4L6 7Zm0 0h12M9 11h6M10 15h4"/>',
      transfer: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 12h18M8 5v7m8-7v7M7 19v2m10-2v2M6 16h1m10 0h1"/>',
      chevron: '<path d="m9 5 7 7-7 7"/>',
      location: '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
      clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
    };
    return '<svg class="line-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[code] || paths.all) + '</svg>';
  }
  function activeMenuPath() {
    if (state.cat === 'all') return 'Все услуги';
    var label = TREE_LABEL[state.cat] || catBy(state.cat).label;
    var sub = state.sub && subBy(state.cat, state.sub);
    return label + (sub ? ' / ' + sub.label : '');
  }
  function menuSwitcher() {
    return '<section class="menu-preview wrap" aria-label="Предпросмотр меню"><div class="menu-preview-row"><span><strong>V7 · категории с фото</strong><small>Точечное обновление V6</small></span><div class="menu-mode-switch" role="group" aria-label="Вид меню"><button type="button" data-menu-mode="sidebar" aria-pressed="' + (state.menuMode === 'sidebar') + '">Боковая панель</button><button type="button" data-menu-mode="panel" aria-pressed="' + (state.menuMode === 'panel') + '">Кнопка каталога</button></div></div><details class="menu-explain"><summary>Что изменено и какое меню я рекомендую</summary><p>Карточки — середина между информативным первым вариантом V5 и крупными фото второго: две просторные колонки рядом с боковой панелью, фото 16:11, вся информация остаётся под снимком. Показываем по 12 примеров: ровные ряды при двух и трёх колонках.</p><p><strong>Рекомендую боковую панель:</strong> разделы с тематическими фотоминиатюрами, счётчиками и последовательным раскрытием; подкатегории — нормальными строками без мелкого дерева. <strong>Кнопка каталога</strong> освобождает ширину сетки: разделы и виды отдыха выбираются в отдельной двухпанельной форме. На телефоне оба варианта открываются кнопкой «Категории».</p><p>Переключается только меню — не карточки, данные или фильтры. Это тестовая страница по прямой ссылке: в меню сайта её нет, заявки не отправляются и оплата не подключается.</p></details></section>';
  }
  var CATEGORY_PHOTOS = {
    adventure: {key: "raft", alt: "Приключения: сплав на рафте — иллюстрация категории"},
    offroad: {key: "jeep2", alt: "Джип-туры и техника: внедорожник на лесной дороге — иллюстрация"},
    guides: {key: "hike", alt: "Гиды и культура: лесная тропа для прогулок с гидом — иллюстрация"},
    animals_farms: {key: "horse", alt: "Животные и фермы: конная прогулка в горах — иллюстрация"},
    food: {key: "khachapuri", alt: "Еда и дегустации: горячая выпечка — иллюстрация категории"},
    stay: {key: "camp", alt: "Где жить: палатка в лесу — иллюстрация отдыха с ночёвкой"},
    rental: {key: "bike", alt: "Прокат: велосипедная прогулка — иллюстрация категории"},
    transfer: {key: "minibus", alt: "Трансферы и поездки: микроавтобус в горах — иллюстрация"}
  };
  function categoryPhoto(code) {
    var photo = CATEGORY_PHOTOS[code];
    if (!photo) return '';
    return '<span class="category-photo" data-photo="' + photo.key + '"><img width="80" height="80" src="' + photoSrc(photo.key) + '" alt="' + escapeHtml(photo.alt) + '" decoding="async"></span>';
  }
  function categoryRows(scope) {
    var html = '<button type="button" class="section-row all-services' + (state.cat === 'all' ? ' selected' : '') + '" data-menu-all="true">' + menuIcon('all') + '<span class="section-label">Все услуги</span><span class="section-count">92</span></button>';
    sellCats().forEach(function (cat) {
      var expanded = state.menuExpanded === cat.code;
      html += '<div class="section-group' + (state.cat === cat.code ? ' selected-group' : '') + '"><button type="button" id="' + scope + '-cat-' + cat.code + '" class="section-row' + (state.cat === cat.code ? ' selected' : '') + '" data-menu-cat="' + cat.code + '" aria-expanded="' + expanded + '">' + categoryPhoto(cat.code) + '<span class="section-label">' + escapeHtml(TREE_LABEL[cat.code] || cat.label) + '</span><span class="section-count">' + offerCount(cat.code) + '</span><span class="section-chevron' + (expanded ? ' expanded' : '') + '">' + menuIcon('chevron') + '</span></button>';
      if (scope === 'side' && expanded) html += '<div class="accordion-content" aria-label="Виды отдыха в разделе">' + subcategoryRows(cat.code) + '</div>';
      html += '</div>';
    });
    return html;
  }
  function subcategoryRows(code) {
    var cat = catBy(code);
    if (!cat) return '';
    var html = '<button type="button" class="subcategory-row' + (state.cat === code && !state.sub ? ' selected' : '') + '" data-treesub="' + code + ':"><span>Все в разделе</span><span>' + offerCount(code) + '</span></button>';
    cat.subs.forEach(function (sub) {
      var n = offerCount(code, sub.code);
      html += '<button type="button" class="subcategory-row' + (state.sub === sub.code ? ' selected' : '') + '" data-treesub="' + code + ':' + sub.code + '"' + (n ? '' : ' disabled') + '><span>' + escapeHtml(sub.label) + '</span><span>' + (n || 'пока нет') + '</span></button>';
    });
    return html;
  }
  function menuView() {
    var mobile = '<button type="button" class="mobile-categories-button" data-action="open-category-menu" aria-haspopup="dialog" aria-expanded="' + state.menuOpen + '">' + menuIcon('all') + '<strong>Категории</strong><span>' + escapeHtml(activeMenuPath()) + '</span>' + menuIcon('chevron') + '</button>';
    if (state.menuMode === 'panel') return mobile + '<nav class="catalog-toolbar" aria-label="Выбранный раздел"><button type="button" class="catalog-open" data-action="open-category-menu" aria-haspopup="dialog" aria-expanded="' + state.menuOpen + '">' + menuIcon('all') + 'Каталог услуг' + menuIcon('chevron') + '</button><span class="active-menu-path">' + escapeHtml(activeMenuPath()) + '</span><button type="button" class="linkish" data-action="reset">Сбросить</button></nav>';
    return mobile + '<aside class="category-sidebar" aria-label="Категории услуг"><div class="sidebar-heading"><h2>Категории</h2><button type="button" class="linkish" data-action="reset">Сбросить</button></div><nav>' + categoryRows('side') + '</nav><button type="button" class="structure-link" data-action="open-structure">Структура каталога 9 × 48</button></aside>';
  }
  function categoryMenuOverlay() {
    if (!state.menuOpen) return '';
    var code = state.menuExpanded || (state.cat !== 'all' ? state.cat : 'adventure');
    var cat = catBy(code);
    return '<div class="category-overlay"><section class="category-dialog" role="dialog" aria-modal="true" aria-labelledby="category-dialog-title" data-step="' + state.menuStep + '"><header class="category-dialog-header"><div><span class="eyebrow">Найдите своё впечатление</span><h2 id="category-dialog-title">Каталог услуг</h2></div><button type="button" id="close-category-menu" class="btn btn-ghost" data-action="close-category-menu" aria-label="Закрыть категории">Закрыть ×</button></header><div class="category-dialog-body"><nav class="drawer-sections" aria-label="Разделы">' + categoryRows('drawer') + '</nav><div class="drawer-subcategories"><button type="button" class="mobile-sections-back" data-action="menu-sections">← Все разделы</button><span class="eyebrow">Вид отдыха</span><h3>' + escapeHtml(TREE_LABEL[code] || cat.label) + '</h3><p class="note">' + escapeHtml(cat.blurb) + '</p><div class="drawer-subcategory-list">' + subcategoryRows(code) + '</div></div></div><footer class="category-dialog-footer"><button type="button" class="linkish" data-action="reset">Сбросить все фильтры</button><button type="button" class="linkish" data-action="menu-structure">Вся структура 9 × 48</button><span>Наличие мест уточняется</span></footer></section></div>';
  }
  function cardHtml(o, reason) {
    var sub = subBy(o.cat, o.sub);
    return '<button type="button" class="card" data-open="' + o.id + '" aria-label="Подробнее: ' + escapeHtml(o.title) + '"><div class="cover"><img class="cover-img" width="640" height="440" src="' + photoSrc(o.photo) + '" alt="Иллюстрация: ' + escapeHtml(o.title) + '" loading="lazy"><span class="badge-ex card-example">Пример</span></div><div class="body"><span class="card-kind">' + escapeHtml(sub ? sub.label : o.sub) + '</span><h3>' + escapeHtml(o.title) + '</h3><div class="card-meta"><span class="meta">' + menuIcon('location') + escapeHtml(o.area) + '</span><span class="card-duration">' + menuIcon('clock') + escapeHtml(o.duration) + '</span></div><p class="card-condition">По запросу · доступность уточняется</p>' + (typeof reason === 'string' ? '<p class="card-relation">' + escapeHtml(reason) + '</p>' : '') + '<div class="card-foot"><div class="price-row"><div><div class="price">' + rub(o.price) + '</div><div class="unit">' + escapeHtml(o.unitLabel) + '</div></div></div><span class="card-action">Подробнее <span aria-hidden="true">→</span></span></div></div></button>';
  }
  function closeCategoryMenu() {
    state.menuOpen = false;render();
    var opener = document.querySelector(window.innerWidth <= 760 ? '.mobile-categories-button' : '.catalog-open');
    if (opener) opener.focus({preventScroll:true});
  }

  function catalogView() {
    var list = filteredOffers(), shown = list.slice(0, state.shown);
    var html = crumbs() + '<div class="catalog-heading"><div><span class="eyebrow">Впечатления АдыГида</span><h1 class="page-title">Чем заняться в Адыгее?</h1><p class="lead">Найдите свой день: горы, вода, новые вкусы или спокойный отдых.</p></div><span class="catalog-total">92 демо-примера<br><small>8 активных разделов</small></span></div>';
    html += '<div class="catalog-shell">' + menuView() + '<div class="catalog-results"><div class="filters"><label class="search-label"><span class="sr-only">Поиск по каталогу</span><input id="search-q" type="search" placeholder="Например, джиппинг или сыр" value="' + escapeHtml(state.query) + '" autocomplete="off"></label><label class="check"><input id="family-toggle" type="checkbox"' + (state.family ? ' checked' : '') + '> С детьми — уточнить</label><button type="button" class="reset" data-action="reset">Сбросить</button></div>';
    html += '<div class="results-heading"><p class="result-count" aria-live="polite">Показаны ' + shown.length + ' из ' + list.length + ' примеров.</p><span class="availability-note">Доступность уточняется</span></div>';
    html += shown.length ? '<div class="grid catalog-grid">' + shown.map(function (o) { return cardHtml(o); }).join('') + '</div>' : '<div class="empty-state"><h2>Ничего не нашлось</h2><p>Попробуйте другой запрос или сбросьте фильтры.</p><button type="button" class="btn btn-primary" data-action="reset">Сбросить фильтры</button></div>';
    if (list.length > shown.length) html += '<div class="more-row"><button type="button" class="btn btn-primary" data-action="more">Показать ещё ' + Math.min(PAGE, list.length - shown.length) + '</button><p class="note">Ваши фильтры сохранятся при просмотре карточек</p></div>';
    html += '</div></div><section class="section"><h2>От идеи до поездки — без спешки</h2><div class="how">';
    [["01 · Заявка", "Выбираете впечатление, желаемую дату и состав."], ["02 · Ручная проверка", "Уточняем возможность и условия у организатора."], ["03 · Согласование", "Сначала предложение с разбивкой, потом сервисный сбор."], ["04 · Детали поездки", "После согласования и оплаты сбора. Остаток — на месте."]].forEach(function (step) {html += '<article><h3>' + step[0] + '</h3><p class="muted">' + step[1] + '</p></article>';});
    return html + '</div></section>';
  }
  function relatedOffers(o) {
    return OFFERS.filter(function (x) {return x.id !== o.id && (x.cat === o.cat || x.area === o.area);}).map(function (x, index) {
      return { offer: x, score: (x.sub === o.sub ? 100 : 0) + (x.cat === o.cat ? 20 : 0) + (x.area === o.area ? 10 : 0), index: index,
        reason: x.sub === o.sub ? 'Тот же вид отдыха' : x.cat === o.cat ? 'В том же разделе' : 'Тот же район в демо' };
    }).sort(function (a, b) {return b.score - a.score || a.index - b.index;}).slice(0, 4);
  }
  function relatedSection(o) {
    return '<section id="related-services" class="section related-section" tabindex="-1"><div class="section-heading"><div><span class="eyebrow">Можно посмотреть ещё</span><h2>Похожие услуги</h2></div><span class="note">По виду отдыха и району</span></div><p class="note">Простая связь по категории и условному району, не персональная рекомендация и не проверка доступности.</p><div class="grid related-grid">' + relatedOffers(o).map(function (r) {return cardHtml(r.offer, r.reason);}).join('') + '</div></section>';
  }
  function detailView() {
    var o = offerBy(state.selectedId), cat = catBy(o.cat), sub = subBy(o.cat, o.sub);
    var html = '<nav class="detail-breadcrumb" aria-label="Навигация карточки"><button type="button" data-action="catalog-return">Каталог впечатлений</button><span aria-hidden="true">/</span><span>' + escapeHtml(TREE_LABEL[o.cat] || cat.label) + '</span></nav><div class="detail-top-actions">' +
      (detailStack.length ? '<button type="button" class="btn btn-ghost" data-action="detail-back">← К предыдущей услуге</button>' : '') + '<button type="button" class="btn btn-ghost" data-action="catalog-return">← Вернуться к каталогу</button></div>';
    html += '<div class="detail"><div><img class="hero-photo" width="640" height="426" src="' + photoSrc(o.photo) + '" alt="Иллюстративное фото: ' + escapeHtml(o.title) + '"><p class="note">Иллюстрация типа активности, не фото конкретного предложения в Адыгее.</p></div><div><span class="badge-ex">Пример</span> <span class="detail-kind">' + escapeHtml(sub.label) + '</span><h1 class="page-title">' + escapeHtml(o.title) + '</h1><p class="muted">' + escapeHtml(o.area) + ' · ' + escapeHtml(o.duration) + '</p><p>' + escapeHtml(o.blurb) + '</p><div class="price-lg">' + rub(o.price) + '</div><p class="note">' + escapeHtml(o.unitLabel) + ' · вымышленная цена для макета</p><div class="btn-row"><button type="button" class="btn btn-primary" data-action="start-request">Оставить демо-заявку</button><button type="button" class="btn btn-ghost" data-action="related-jump">Похожие услуги ↓</button></div><p class="note">Сначала уточняем условия. Места и цена не подтверждены.</p></div></div>';
    html += '<div class="facts"><div class="block"><h3>Что входит</h3><p class="muted">В боевой версии уточняется с организатором. В демо не придумываем состав услуги.</p></div><div class="block"><h3>Кому подходит</h3><p class="muted">Возраст, подготовка и ограничения уточняются до записи.</p></div><div class="block"><h3>Место встречи</h3><p class="muted">' + escapeHtml(o.area) + '. Точная точка в демо не задаётся.</p></div><div class="block"><h3>Условия отмены</h3><p class="muted">Появятся после согласования с партнёром; сейчас правила не выдумываем.</p></div></div><div class="detail-money">' + moneyBox(o, state.party, state.nights) + '</div>';
    html += relatedSection(o);
    html += '<div class="detail-bottom"><div><strong>Продолжим выбирать?</strong><p class="note">Вернём ваши фильтры и место в каталоге.</p></div><button type="button" class="btn btn-primary" data-action="catalog-return" id="detail-bottom-back">← Вернуться к каталогу</button></div><nav class="mobile-back" aria-label="Быстрый возврат"><button type="button" data-action="catalog-return">← Каталог</button><button type="button" data-action="related-jump">Похожие услуги</button>' + (detailStack.length ? '<button type="button" data-action="detail-back">← Назад</button>' : '') + '</nav>';
    return html;
  }
  function returnCatalog() {
    state.view = 'catalog'; state.error = ''; detailStack = [];
    render();
    var button = catalogFocusId && document.querySelector('[data-open="' + catalogFocusId + '"]');
    if (button) button.focus({ preventScroll: true });
    window.scrollTo(0, catalogY);
  }
  function detailBack() {
    var previous = detailStack.pop();
    if (!previous) {returnCatalog();return;}
    state.selectedId = previous.id;state.view = 'detail';state.stage = 'form';state.error = '';
    render();window.scrollTo(0, previous.y);
  }
  function go(view) {
    if (view === 'catalog') {returnCatalog();return;}
    state.view = view;if (view !== 'request') state.error = '';
    render();window.scrollTo(0, 0);
  }
  function openOffer(id) {
    if (state.view === 'catalog') {catalogY = window.scrollY || 0;catalogFocusId = id;detailStack = [];}
    else if (state.view === 'detail') detailStack.push({id: state.selectedId, y: window.scrollY || 0});
    state.selectedId = id;state.stage = 'form';state.error = '';state.view = 'detail';
    render();window.scrollTo(0, 0);
  }

  function header() {
    return '<header class="site-header"><div class="wrap"><div class="header-row">' +
      '<button type="button" class="brand" data-go="catalog" aria-label="АдыГид — к каталогу">' + logo() + '<span class="brand-word">АдыГид</span></button>' +
      '<span class="header-subtitle">Впечатления · тестовый каталог</span><span class="v7-mark">Тест</span></div></div></header>';
  }
  function crumbs() {
    var parts = ['<button type="button" data-crumb="all">Все впечатления</button>'];
    if (state.cat !== "all") {
      var c = catBy(state.cat);
      parts.push('<span class="sep">/</span><button type="button" data-crumb="cat">' + escapeHtml(c ? (TREE_LABEL[c.code] || c.label) : state.cat) + "</button>");
    }
    if (state.sub) {
      var s = subBy(state.cat, state.sub);
      parts.push('<span class="sep">/</span><span>' + escapeHtml(s ? s.label : state.sub) + "</span>");
    }
    return '<div class="crumbs">' + parts.join("") + "</div>";
  }
  function requestView() {
    var o = offerBy(state.selectedId);
    var b = breakdown(o, state.party, state.nights);
    var html = '<div class="btn-row" style="margin-bottom:16px">' +
      '<button type="button" class="btn btn-ghost" data-action="back-detail">К карточке</button>' +
      '<button type="button" class="btn btn-ghost" data-go="catalog">К каталогу</button></div>';
    html += '<p class="muted">Демо-заявка · Демо V7</p>';
    html += '<h1 class="page-title">' + escapeHtml(o.title) + "</h1>";
    html += '<p class="lead">Укажите пожелания. Наличие мест неизвестно. Кнопка ниже ничего не отправляет — ни в базу, ни на почту, ни партнёру. Цена ориентировочная и вымышлена.</p>';
    html += '<div class="stage-bar"><p class="muted">Переключатель стадий только для просмотра демо. Основной путь идёт только вперёд.</p><div class="chips">';
    STAGES.forEach(function (s) {
      html += '<button type="button" class="chip' + (state.stage === s.id ? " active" : "") + '" data-stage="' + s.id + '">' + s.label + "</button>";
    });
    html += "</div></div>";
    if (state.stage === "form") {
      html += '<div class="detail"><div>';
      html += '<div class="field"><label for="wish-date">Желаемая дата — можно оставить пустой</label>';
      html += '<input id="wish-date" type="text" value="' + escapeHtml(state.wishDate) + '" placeholder="например, ' + EXAMPLE_DATE + '" autocomplete="off"></div>';
      html += '<div class="btn-row" style="margin-bottom:16px"><button type="button" class="btn btn-ghost" data-action="fill-date">Подставить ' + EXAMPLE_DATE + "</button></div>";
      html += '<p class="muted" style="margin:0 0 8px">Участников: ' + state.party + " " + peopleWord(state.party) + "</p>";
      html += '<div class="stepper"><button type="button" class="btn btn-ghost" data-action="party-dec"' + (state.party <= 1 ? " disabled" : "") + ">−</button>";
      html += '<span class="n">' + state.party + "</span>";
      html += '<button type="button" class="btn btn-ghost" data-action="party-inc"' + (state.party >= 8 ? " disabled" : "") + ">+</button></div>";
      if (o.unit === "night") {
        html += '<p class="muted" style="margin:16px 0 8px">Суток: ' + state.nights + " " + nightsWord(state.nights) + "</p>";
        html += '<div class="stepper"><button type="button" class="btn btn-ghost" data-action="nights-dec"' + (state.nights <= 1 ? " disabled" : "") + ">−</button>";
        html += '<span class="n">' + state.nights + "</span>";
        html += '<button type="button" class="btn btn-ghost" data-action="nights-inc"' + (state.nights >= 7 ? " disabled" : "") + ">+</button></div>";
      }
      if (state.error) html += '<div class="warn">' + escapeHtml(state.error) + "</div>";
      html += '<div style="margin-top:16px"><button type="button" class="btn btn-primary" data-action="submit">Отправить демо-заявку</button></div>';
      html += '<p class="muted" style="margin:12px 0 0">Контакты, телефон и карту не просим. Кнопка ничего не отправляет — только показывает следующий шаг демо.</p></div>' + moneyBox(o, state.party, state.nights) + "</div>";
    }
    if (state.stage === "checking") {
      html += '<div class="block" style="max-width:640px"><span class="badge-ex">Демо · Проверяем возможность</span>';
      html += "<h2>Заявка никуда не отправлена</h2>";
      html += "<p>В боевом режиме на этом шаге АдыГид связывается с организатором. Сейчас заявка не отправлена: ни письма, ни сообщения, ни записи в базу.</p>";
      html += '<p class="muted">' + escapeHtml(o.title) + " · " + escapeHtml(state.wishDate || "дата не указана") + " · " + state.party + " " + peopleWord(state.party) +
        (o.unit === "night" ? " · " + state.nights + " " + nightsWord(state.nights) : "") + "</p>";
      html += '<div class="info">Оплату ещё не предлагаем. Если организатор не подтвердил заявку, сервисный сбор оплачивать нельзя.</div>';
      html += '<button type="button" class="btn btn-primary" data-stage-fwd="offer">Показать стадию «Предложение»</button></div>';
    }
    if (state.stage === "offer") {
      html += '<div class="detail"><div class="block"><span class="badge-ex">Демо · Предложение для согласования</span>';
      html += "<h2>Так выглядело бы согласованное предложение</h2>";
      html += "<p>" + escapeHtml(o.title) + ". Желаемая дата: " + escapeHtml(state.wishDate || "не указана") + ". Участников: " + state.party + " " + peopleWord(state.party) +
        (o.unit === "night" ? ". Суток: " + state.nights + "." : "") + "</p>";
      html += '<div class="btn-row"><button type="button" class="btn btn-primary" data-stage-fwd="pay">Согласиться и перейти к оплате сбора</button>';
      html += '<button type="button" class="btn btn-ghost" data-action="decline">Отклонить в демо</button></div></div>';
      html += moneyBox(o, state.party, state.nights) + "</div>";
    }
    if (state.stage === "pay") {
      html += '<div class="block" style="max-width:640px"><span class="badge">Имитация · оплата не производится</span>';
      html += "<h2>Оплата сервисного сбора " + rub(b.fee) + "</h2>";
      html += "<p>Турист оплачивает только сбор АдыГиду, не всю стоимость и не предоплату организатору. Остаток " + rub(b.onsite) + " — на месте, уже со скидкой партнёра.</p>";
      html += '<div class="warn">Платёжная форма не открывается. Данные карты не запрашиваем.</div>';
      html += '<button type="button" class="btn btn-primary" data-stage-fwd="done">Показать стадию после имитации оплаты ' + rub(b.fee) + "</button></div>";
    }
    if (state.stage === "done") {
      html += '<div class="block" style="max-width:640px"><span class="badge-ex">Демо-состояние · не подтверждённая бронь</span>';
      html += "<h2>Так выглядело бы итоговое подтверждение</h2>";
      html += "<p>В боевом режиме турист получил бы детали встречи только после реального платежа и согласия партнёра. Сейчас заявка не подтверждена, контакты не показываем.</p>";
      html += '<p class="muted">' + escapeHtml(o.title) + " · " + escapeHtml(state.wishDate || "дата не указана") + " · сбор " + rub(b.fee) + " · на месте " + rub(b.onsite) + "</p>";
      html += '<button type="button" class="btn btn-primary" data-go="catalog">Вернуться к каталогу</button></div>';
    }
    return html;
  }
  function structureOverlay() {
    if (!state.structure) return "";
    var html = '<div class="overlay" data-action="close-structure" role="dialog" aria-modal="true" aria-labelledby="tax-title">';
    html += '<div class="overlay-card" data-stop="1"><div class="btn-row" style="justify-content:space-between;margin-bottom:8px"><h2 id="tax-title" style="margin:0">Все категории</h2>';
    html += '<button type="button" class="btn btn-ghost" data-action="close-structure">Закрыть</button></div>';
    html += '<p class="muted" style="margin:0 0 16px">Плановая сетка: 9 разделов и 48 подкатегорий. Термы в продаже не участвуют, но в структуре остаются. Параплан — без карточек для бронирования. Зелёным отмечены подкатегории, у которых в этом демо есть примеры.</p>';
    TAXONOMY.forEach(function (c) {
      html += '<div class="tax-cat"><h3>' + escapeHtml(c.label) + (c.sell ? "" : ' <span class="badge">отложено, не в продаже</span>') + "</h3>";
      html += '<div class="tax-subs">';
      c.subs.forEach(function (s) {
        var n = offerCount(c.code, s.code);
        html += "<span class=\"" + (n ? "has" : "") + "\">" + escapeHtml(s.label) + (n ? " · " + n : (s.code === "sky" ? " · без примеров" : " · пусто")) + "</span>";
      });
      html += "</div></div>";
    });
    html += "</div></div>";
    return html;
  }
  function render() {
    var root = document.getElementById("app");
    var active = document.activeElement;
    var activeId = active && active.id;
    var start = active && typeof active.selectionStart === "number" ? active.selectionStart : null;
    var end = active && typeof active.selectionEnd === "number" ? active.selectionEnd : null;
    document.body.setAttribute("data-menu-mode", state.menuMode);
    document.body.setAttribute("data-menu-open", String(state.menuOpen));
    document.body.setAttribute("data-view", state.view);
    var oldExplain = document.querySelector(".menu-explain");
    var explainOpen = oldExplain && oldExplain.open;
    var body = state.view === "detail" ? detailView() : state.view === "request" ? requestView() : catalogView();
    root.innerHTML = header() + menuSwitcher() + '<main class="wrap">' + body + "</main>" + structureOverlay() + categoryMenuOverlay();
    var explain = document.querySelector(".menu-explain");
    if (explain) explain.open = !!explainOpen;
    if (activeId) {
      var el = document.getElementById(activeId);
      if (el) {
        el.focus();
        if (start !== null && el.setSelectionRange) { try { el.setSelectionRange(start, end); } catch (err) {} }
      }
    }
  }
  function setCat(code) {
    state.cat = code; state.sub = ""; state.shown = PAGE; state.view = "catalog"; render();
  }
  function resetFilters() {
    state.cat = "all"; state.sub = ""; state.query = ""; state.family = false; state.shown = PAGE; render();
  }
  function submitDemo() {
    var parsed = parseWishDate(state.wishDate);
    if (parsed.kind === "invalid") { state.error = "Дату не разобрали. Оставьте поле пустым или напишите, например: " + EXAMPLE_DATE + "."; render(); return; }
    if (parsed.kind === "past") { state.error = "Если указываете дату, она должна быть не раньше сегодняшней. Можно оставить поле пустым."; render(); return; }
    state.error = ""; state.stage = "checking"; render();
  }
  function onClick(e) {
    if (e.target.classList && e.target.classList.contains("category-overlay")) {closeCategoryMenu();return;}
    if (e.target.classList && e.target.classList.contains("overlay")) { state.structure = false; render(); return; }
    var t = e.target.closest("button[data-menu-mode], [data-menu-cat], [data-menu-all], [data-go], [data-action], [data-open], [data-cat], [data-crumb], [data-stage], [data-stage-fwd], [data-treesub]");
    if (!t) return;
    if (t.hasAttribute("data-menu-mode")) {
      var mode = t.getAttribute("data-menu-mode");
      if (mode === "sidebar" || mode === "panel") {
        var y = window.scrollY || 0;state.menuMode = mode;state.menuOpen = false;render();
        var selectedMode = document.querySelector('button[data-menu-mode="' + mode + '"]');
        if (selectedMode) selectedMode.focus({preventScroll:true});window.scrollTo(0,y);
      }
      return;
    }
    if (t.hasAttribute("data-menu-all")) {state.menuOpen = false;state.menuExpanded = "";setCat("all");return;}
    if (t.hasAttribute("data-menu-cat")) {
      var code = t.getAttribute("data-menu-cat");
      if (!catBy(code) || !catBy(code).sell) return;
      var same = state.cat === code;
      if (!same) {state.cat = code;state.sub = "";state.shown = PAGE;}
      state.menuExpanded = same && state.menuExpanded === code && !state.menuOpen ? "" : code;
      state.menuStep = "subs";render();return;
    }
    if (t.getAttribute("data-go")) { go(t.getAttribute("data-go")); return; }
    var action = t.getAttribute("data-action");
    if (action === "open-category-menu") {
      state.menuOpen = true;state.menuStep = "sections";
      state.menuExpanded = state.cat !== "all" ? state.cat : "adventure";render();
      var closeButton = document.getElementById("close-category-menu");if (closeButton) closeButton.focus();return;
    }
    if (action === "close-category-menu") {closeCategoryMenu();return;}
    if (action === "menu-sections") {state.menuStep = "sections";render();return;}
    if (action === "menu-structure") {state.menuOpen = false;state.structure = true;render();return;}
    if (action === "reset") {state.menuOpen = false;state.menuExpanded = "";resetFilters();return;}
    if (action === "catalog-return") {returnCatalog();return;}
    if (action === "detail-back") {detailBack();return;}
    if (action === "related-jump") {
      var section = document.getElementById("related-services");
      if (section) {section.focus({preventScroll:true});section.scrollIntoView({behavior:"auto",block:"start"});}
      return;
    }
    if (action === "open-structure") { state.structure = true; render(); return; }
    if (action === "close-structure") { state.structure = false; render(); return; }
    if (action === "reset") { resetFilters(); return; }
    if (action === "more") { state.shown += PAGE; render(); return; }
    if (action === "start-request") { state.stage = "form"; state.error = ""; go("request"); return; }
    if (action === "back-detail") { go("detail"); return; }
    if (action === "fill-date") { state.wishDate = EXAMPLE_DATE; state.error = ""; render(); return; }
    if (action === "party-dec") { state.party = Math.max(1, state.party - 1); render(); return; }
    if (action === "party-inc") { state.party = Math.min(8, state.party + 1); render(); return; }
    if (action === "nights-dec") { state.nights = Math.max(1, state.nights - 1); render(); return; }
    if (action === "nights-inc") { state.nights = Math.min(7, state.nights + 1); render(); return; }
    if (action === "submit") { submitDemo(); return; }
    if (action === "decline") { state.stage = "form"; render(); return; }
    if (t.getAttribute("data-open")) { openOffer(t.getAttribute("data-open")); return; }
    if (t.getAttribute("data-cat")) { setCat(t.getAttribute("data-cat")); return; }
    if (t.getAttribute("data-treesub")) {
      var parts = t.getAttribute("data-treesub").split(":");
      state.cat = parts[0]; state.sub = parts[1]; state.shown = PAGE; state.view = "catalog"; state.menuOpen = false; state.menuExpanded = parts[0]; render(); return;
    }
    if (t.getAttribute("data-crumb") === "all") { setCat("all"); return; }
    if (t.getAttribute("data-crumb") === "cat") { state.sub = ""; state.shown = PAGE; render(); return; }
    if (t.getAttribute("data-stage-fwd")) {
      var next = t.getAttribute("data-stage-fwd");
      if (STAGE_ORDER.indexOf(next) === STAGE_ORDER.indexOf(state.stage) + 1) { state.stage = next; render(); }
      return;
    }
    if (t.getAttribute("data-stage")) { state.stage = t.getAttribute("data-stage"); render(); }
  }
  function onInput(e) {
    if (e.target.id === "search-q") { state.query = e.target.value; state.shown = PAGE; render(); return; }
    if (e.target.id === "wish-date") { state.wishDate = e.target.value; if (state.error) state.error = ""; render(); }
  }
  function onChange(e) {
    if (e.target.id === "family-toggle") { state.family = !!e.target.checked; state.shown = PAGE; render(); }
  }
  document.getElementById("app").addEventListener("click", onClick);
  document.getElementById("app").addEventListener("input", onInput);
  document.getElementById("app").addEventListener("change", onChange);
  document.addEventListener("keydown", function (e) {
    if (state.menuOpen && e.key === "Escape") {e.preventDefault();closeCategoryMenu();return;}
    if (state.menuOpen && e.key === "Tab") {
      var dialog = document.querySelector(".category-dialog");
      var buttons = Array.prototype.slice.call(dialog.querySelectorAll("button:not([disabled])")).filter(function (button) {
        if (window.innerWidth > 760) return !button.classList.contains("mobile-sections-back");
        if (state.menuStep === "subs" && button.closest(".drawer-sections")) return false;
        if (state.menuStep === "sections" && button.closest(".drawer-subcategories")) return false;
        return true;
      });
      var first = buttons[0], last = buttons[buttons.length - 1];
      if (e.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {e.preventDefault();last.focus();}
      else if (!e.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {e.preventDefault();first.focus();}
    }
    if (e.key === "Escape" && state.structure) { state.structure = false; render(); }
  });
  function validateCatalog() {
    if (OFFERS.length !== 92) throw new Error("Ожидалось 92 демо-примера");
    var ids = new Set();
    OFFERS.forEach(function (o) {
      if (ids.has(o.id)) throw new Error("Повтор id: " + o.id);
      ids.add(o.id);
      if (!catBy(o.cat) || !catBy(o.cat).sell || !subBy(o.cat, o.sub) || o.sub === "sky") throw new Error("Неверная категория: " + o.id);
      if (PHOTO_KEYS.indexOf(o.photo) === -1 || !/\/[a-z0-9]+\.webp(?:\?|$)/.test(photoSrc(o.photo))) throw new Error("Нет фото: " + o.id);
    });
  }
  validateCatalog();
  var subTotal = TAXONOMY.reduce(function (n, c) { return n + c.subs.length; }, 0);
  if (TAXONOMY.length !== 9 || subTotal !== 48) console.warn("Taxonomy count mismatch:", TAXONOMY.length, subTotal);
  render();
})();

