# Підсумок прогону `lite`

Модель: gemini-3.5-flash-lite

| Варіант | Файлів | Правильно | Помилок | Пропусків | Вигадок | Спіймано правилами | Тихих помилок | Рішення збіглося | Помилок виклику | Токени запиту | Токени всього |
|---|---|---|---|---|---|---|---|---|---|---|---|
| clean | 9 | 275 | 8 | 0 | 0 | 0 | 2 | 9/9 | 0 | 1769 | 2311 |
| blur | 3 | 124 | 2 | 0 | 0 | 0 | 2 | 3/3 | 0 | 1769 | 2463 |
| lowres | 3 | 122 | 4 | 0 | 0 | 0 | 4 | 3/3 | 0 | 1769 | 2464 |
| jpeg | 3 | 122 | 4 | 0 | 0 | 0 | 4 | 3/3 | 0 | 1769 | 2464 |
| faded | 3 | 119 | 7 | 0 | 0 | 0 | 6 | 3/3 | 0 | 1769 | 2463 |
| photo | 3 | 123 | 3 | 0 | 0 | 0 | 2 | 3/3 | 0 | 1757 | 2451 |
| crop | 3 | 120 | 6 | 0 | 0 | 0 | 0 | 3/3 | 0 | 1763 | 2427 |
| **разом** | 27 | 1005 | 34 | 0 | 0 | 0 | 20 | 27/27 | 0 | 1767 | 2407 |

## Критичні поля (IBAN, код постачальника, до сплати)

| Варіант | Правильно | Помилок | Пропусків | Вигадок |
|---|---|---|---|---|
| clean | 27 | 0 | 0 | 0 |
| blur | 9 | 0 | 0 | 0 |
| lowres | 9 | 0 | 0 | 0 |
| jpeg | 9 | 0 | 0 | 0 |
| faded | 9 | 0 | 0 | 0 |
| photo | 9 | 0 | 0 | 0 |
| crop | 9 | 0 | 0 | 0 |

## Матриця рішень (очікувалось → отримано)

| Очікувалось | auto | review | reject | помилка |
|---|---|---|---|---|
| auto | 14 | 0 | 0 | 0 |
| review | 0 | 12 | 0 | 0 |
| reject | 0 | 0 | 1 | 0 |

## Середній час за етапами, с

- prepare: 0.074
- extraction: 34.131
- checks: 0.000

## По файлах

| Файл | Очікувалось | Отримано | Правила (error) | Не спрацювали, але мали | Неправильні поля |
|---|---|---|---|---|---|
| clean/nakladna-09.png | reject | reject | document_type | — | items.2.name:помилка |
| clean/rahunok-01.png | auto | auto | — | — | number:помилка |
| clean/rahunok-02.png | auto | auto | — | — | — |
| clean/rahunok-03.png | auto | auto | — | — | items.2.name:помилка |
| clean/rahunok-04.png | auto | auto | — | — | — |
| clean/rahunok-05.png | review | review | arithmetic_line | — | items.2.name:помилка |
| clean/rahunok-06.png | review | review | iban_checksum, iban_registry | — | items.0.name:помилка; items.1.name:помилка |
| clean/rahunok-07.png | review | review | buyer | — | items.0.name:помилка; items.1.name:помилка |
| clean/rahunok-08.png | review | review | iban_registry | — | — |
| degraded/rahunok-01-blur.jpg | auto | auto | — | — | number:помилка |
| degraded/rahunok-01-crop.jpg | review | review | missing_required | — | items.0.name:помилка; items.1.name:помилка; items.2.name:помилка |
| degraded/rahunok-01-faded.jpg | auto | auto | — | — | buyer.name:помилка; items.0.name:помилка; items.1.name:помилка; items.2.name:помилка |
| degraded/rahunok-01-jpeg.jpg | auto | auto | — | — | items.0.name:помилка; items.1.name:помилка; items.2.name:помилка |
| degraded/rahunok-01-lowres.jpg | auto | auto | — | — | items.0.name:помилка; items.1.name:помилка; items.2.name:помилка |
| degraded/rahunok-01-photo.jpg | auto | auto | — | — | number:помилка |
| degraded/rahunok-03-blur.jpg | auto | auto | — | — | items.2.name:помилка |
| degraded/rahunok-03-crop.jpg | review | review | unreadable | — | items.0.name:помилка; items.2.name:помилка; items.8.name:помилка |
| degraded/rahunok-03-faded.jpg | auto | auto | — | — | items.2.name:помилка; items.8.name:помилка |
| degraded/rahunok-03-jpeg.jpg | auto | auto | — | — | items.2.name:помилка |
| degraded/rahunok-03-lowres.jpg | auto | auto | — | — | items.2.name:помилка |
| degraded/rahunok-03-photo.jpg | auto | auto | — | — | items.2.name:помилка |
| degraded/rahunok-05-blur.jpg | review | review | arithmetic_line | — | — |
| degraded/rahunok-05-crop.jpg | review | review | arithmetic_line, missing_required | — | — |
| degraded/rahunok-05-faded.jpg | review | review | arithmetic_line | — | buyer.name:помилка |
| degraded/rahunok-05-jpeg.jpg | review | review | arithmetic_line | — | — |
| degraded/rahunok-05-lowres.jpg | review | review | arithmetic_line | — | — |
| degraded/rahunok-05-photo.jpg | review | review | arithmetic_line | — | items.2.name:помилка |