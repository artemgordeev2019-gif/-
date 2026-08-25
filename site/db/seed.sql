-- Необязательно: перенести стартовые заказы из site/data/state.json в базу.
-- Запускать один раз, в SQL Editor. Существующие строки с теми же id обновятся.

insert into public.orders (id,title,client,category,price,due,status,priority,pay,paid_amount,paid_date,notes) values
 ('o1','Логотип для кофейни «Тёплый угол»','Ирина К.','Логотип',25000,'2026-08-30','work','high','prepay',10000,null,'Три направления: вывеска, стакан, витрина. Ждёт вторую итерацию.'),
 ('o2','Айдентика мастерской керамики','Студия «Глина»','Айдентика',60000,'2026-09-06','new','mid','none',0,null,'Знак, палитра, паттерн, шрифтовая пара, гайд на 12 полос.'),
 ('o3','Буклет к выставке «Сад в августе»','Галерея «Сад»','Полиграфия',18000,'2026-08-27','work','high','prepay',9000,'2026-08-26','Сдать в типографию до 1 сентября.'),
 ('o4','Этикетка для варенья','Ферма «Луг»','Упаковка',14000,'2026-08-14','done','low','full',14000,'2026-08-16',''),
 ('o5','Фирменный стиль пекарни','«Опара»','Айдентика',45000,'2026-07-08','done','mid','full',45000,'2026-07-10',''),
 ('o6','Серия постеров для фестиваля','Фонд «Поле»','Полиграфия',30000,'2026-06-20','done','mid','full',30000,'2026-06-22',''),
 ('o7','Иллюстрации для меню','Ресторан «Тёрн»','Иллюстрация',22000,'2026-05-28','done','low','full',22000,'2026-05-30','')
on conflict (id) do update set
  title = excluded.title, client = excluded.client, category = excluded.category,
  price = excluded.price, due = excluded.due, status = excluded.status,
  priority = excluded.priority, pay = excluded.pay, paid_amount = excluded.paid_amount,
  paid_date = excluded.paid_date, notes = excluded.notes, updated_at = now();
