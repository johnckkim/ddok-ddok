/* 다국어: 우리동네플러스 지원 언어(한국어·English·中文·Tiếng Việt·ไทย·Русский).
   고정 문구는 아래 사전, 답변 속 품목명·규격·지자체명은 /api/translate 로 번역(30일 캐시). */
(function () {
  'use strict';
  var LANGS = [
    { code: 'ko', name: '한국어' }, { code: 'en', name: 'English' }, { code: 'zh', name: '中文' },
    { code: 'vi', name: 'Tiếng Việt' }, { code: 'th', name: 'ไทย' }, { code: 'ru', name: 'Русский' }
  ];

  /* ---------- 국기(이모지 국기는 Windows에서 안 보여 SVG로 그림) ---------- */
  function star(cx, cy, R) {
    var r = R * 0.382, p = [];
    for (var i = 0; i < 10; i++) {
      var a = ((-90 + i * 36) * Math.PI) / 180, d = i % 2 ? r : R;
      p.push((cx + d * Math.cos(a)).toFixed(2) + ',' + (cy + d * Math.sin(a)).toFixed(2));
    }
    return '<polygon points="' + p.join(' ') + '" fill="';
  }
  function gwae(cx, cy, pat, rot) {
    var bar = function (y, solid) {
      return solid ? '<rect x="' + (cx - 4) + '" y="' + y + '" width="8" height="1.1" fill="#000"/>'
        : '<rect x="' + (cx - 4) + '" y="' + y + '" width="3.2" height="1.1" fill="#000"/><rect x="' + (cx + 0.8) + '" y="' + y + '" width="3.2" height="1.1" fill="#000"/>';
    };
    return '<g transform="rotate(' + rot + ' ' + cx + ' ' + cy + ')">' + bar(cy - 2.7, pat[0]) + bar(cy - 0.55, pat[1]) + bar(cy + 1.6, pat[2]) + '</g>';
  }
  var FLAG = {
    ko: '<rect width="30" height="20" fill="#fff"/><g transform="rotate(-33.69 15 10)">' +
      '<path d="M 11 10 A 4 4 0 0 1 19 10 A 2 2 0 0 1 15 10 A 2 2 0 0 0 11 10 Z" fill="#C60C30"/>' +
      '<path d="M 19 10 A 4 4 0 0 1 11 10 A 2 2 0 0 1 15 10 A 2 2 0 0 0 19 10 Z" fill="#003478"/></g>' +
      gwae(6, 4.5, [1, 1, 1], -33.69) + gwae(6, 15.5, [1, 0, 1], 33.69) + gwae(24, 4.5, [0, 1, 0], 33.69) + gwae(24, 15.5, [0, 0, 0], -33.69),
    en: (function () {
      var s = '';
      for (var i = 0; i < 7; i++) s += '<rect y="' + (i * 20 / 7).toFixed(3) + '" width="30" height="' + (20 / 7).toFixed(3) + '" fill="' + (i % 2 ? '#fff' : '#B22234') + '"/>';
      return s + '<rect width="13" height="11" fill="#3C3B6E"/>' + star(6.5, 5.5, 3) + '#fff"/>';
    })(),
    zh: '<rect width="30" height="20" fill="#DE2910"/>' + star(6, 5, 3.2) + '#FFDE00"/>' + star(11.5, 2.5, 1) + '#FFDE00"/>' +
      star(13, 5, 1) + '#FFDE00"/>' + star(13, 8, 1) + '#FFDE00"/>' + star(11.5, 10.5, 1) + '#FFDE00"/>',
    vi: '<rect width="30" height="20" fill="#DA251D"/>' + star(15, 10, 5) + '#FFFF00"/>',
    th: '<rect width="30" height="20" fill="#A51931"/><rect y="3.33" width="30" height="13.33" fill="#F4F5F8"/><rect y="6.66" width="30" height="6.66" fill="#2D2A4A"/>',
    ru: '<rect width="30" height="6.66" fill="#fff"/><rect y="6.66" width="30" height="6.66" fill="#0039A6"/><rect y="13.33" width="30" height="6.66" fill="#D52B1E"/>'
  };
  function flag(code) {
    return '<svg class="flag" viewBox="0 0 30 20" aria-hidden="true">' + (FLAG[code] || FLAG.ko) + '</svg>';
  }

  /* ---------- 고정 문구 [ko, en, zh, vi, th, ru] ---------- */
  var S = {
    title: ['대형폐기물 수수료 안내', 'Bulky Waste Fee Guide', '大件垃圾处理费查询', 'Tra cứu phí rác cồng kềnh', 'ค่าธรรมเนียมทิ้งขยะชิ้นใหญ่', 'Плата за вывоз крупногабаритных отходов'],
    sub: ['품목을 입력하면 AI가 수수료를 알려드립니다', 'Enter an item and AI tells you the disposal fee', '输入物品名称，AI会告诉您处理费', 'Nhập tên đồ vật, AI sẽ cho bạn biết phí', 'พิมพ์ชื่อสิ่งของ แล้ว AI จะบอกค่าธรรมเนียม', 'Введите предмет — ИИ подскажет стоимость вывоза'],
    brandSub: ['수수료 안내', 'Fee Guide', '费用查询', 'Tra cứu phí', 'ค่าธรรมเนียม', 'Тарифы'],
    change: ['변경', 'Change', '更改', 'Đổi', 'เปลี่ยน', 'Изменить'],
    cart: ['장바구니', 'Cart', '购物车', 'Giỏ', 'ตะกร้า', 'Корзина'],
    language: ['언어', 'Language', '语言', 'Ngôn ngữ', 'ภาษา', 'Язык'],
    send: ['보내기', 'Send', '发送', 'Gửi', 'ส่ง', 'Отправить'],
    phPlace: ['거주하고 계신 지자체명 (예: 과천시)', 'Your city/county/district (e.g. Gwacheon)', '您居住的市/郡/区（例：果川市）', 'Thành phố/quận nơi bạn sống (vd: Gwacheon)', 'เมือง/เขตที่คุณอาศัย (เช่น Gwacheon)', 'Ваш город/район (напр. Квачхон)'],
    lblPlace: ['지자체명', 'City/district', '市郡区', 'Thành phố/quận', 'เมือง/เขต', 'Город/район'],
    notePlace: ['시·군·구 이름 일부만 입력해도 됩니다.', 'Part of the name is enough.', '输入部分名称即可。', 'Chỉ cần nhập một phần tên.', 'พิมพ์แค่บางส่วนของชื่อก็ได้', 'Достаточно части названия.'],
    phItems: ['버릴 품목을 입력하세요 (예: 식기세척기, 캣타워)', 'Items to throw away (e.g. dishwasher, cat tower)', '要扔的物品（例：洗碗机、猫爬架）', 'Đồ cần bỏ (vd: máy rửa bát, tháp mèo)', 'สิ่งที่จะทิ้ง (เช่น เครื่องล้างจาน, คอนโดแมว)', 'Что выбрасываете (напр. посудомойка, кошачий домик)'],
    lblItems: ['품목', 'Item', '物品', 'Đồ vật', 'สิ่งของ', 'Предмет'],
    noteItems: ['여러 품목은 쉼표(,)로 구분해 주세요.', 'Separate several items with commas (,).', '多个物品请用逗号（,）分隔。', 'Nhiều món thì cách nhau bằng dấu phẩy (,).', 'หลายรายการให้คั่นด้วยจุลภาค (,)', 'Несколько предметов — через запятую (,).'],
    askPlace: ['<b>거주하고 계신 지자체명</b>을 입력해 주세요.', 'Please enter <b>the city, county or district where you live</b>.', '请输入<b>您居住的市、郡或区</b>。', 'Vui lòng nhập <b>thành phố/quận nơi bạn sống</b>.', 'กรุณาพิมพ์<b>เมือง/เขตที่คุณอาศัยอยู่</b>', 'Введите <b>город или район, где вы живёте</b>.'],
    askPlaceAgain: ['지자체를 바꿀게요. <b>거주하고 계신 지자체명</b>을 입력해 주세요.', 'Let’s change the area. Please enter <b>the city, county or district where you live</b>.', '更改地区。请输入<b>您居住的市、郡或区</b>。', 'Đổi khu vực. Vui lòng nhập <b>thành phố/quận nơi bạn sống</b>.', 'เปลี่ยนพื้นที่ กรุณาพิมพ์<b>เมือง/เขตที่คุณอาศัยอยู่</b>', 'Меняем район. Введите <b>город или район, где вы живёте</b>.'],
    muniSet: ['<b>{m}</b> 기준으로 안내해 드릴게요.<br>버릴 품목을 입력해 주세요. 여러 개는 쉼표(,)로 구분하면 됩니다.',
      'I’ll use the fees of <b>{m}</b>.<br>Enter the items you want to throw away. Separate several items with commas (,).',
      '将按<b>{m}</b>的标准为您说明。<br>请输入要扔的物品，多个物品用逗号（,）分隔。',
      'Tôi sẽ hướng dẫn theo quy định của <b>{m}</b>.<br>Nhập đồ cần bỏ, nhiều món thì cách nhau bằng dấu phẩy (,).',
      'จะแจ้งตามเกณฑ์ของ <b>{m}</b><br>พิมพ์สิ่งที่จะทิ้ง หลายรายการให้คั่นด้วยจุลภาค (,)',
      'Расскажу по тарифам: <b>{m}</b>.<br>Введите, что хотите выбросить. Несколько предметов — через запятую (,).'],
    noArea: ['아직 안내하지 않는 지역이에요. 시·군·구 이름을 다시 확인해 주세요. (현재 {n}곳 안내)', 'We don’t cover that area yet. Please check the name. ({n} areas covered)', '暂不支持该地区，请确认名称。（目前支持{n}个地区）', 'Chưa hỗ trợ khu vực này. Vui lòng kiểm tra lại tên. (Hiện có {n} khu vực)', 'ยังไม่รองรับพื้นที่นี้ กรุณาตรวจสอบชื่ออีกครั้ง (รองรับ {n} พื้นที่)', 'Этот район пока не поддерживается. Проверьте название. (Доступно районов: {n})'],
    needPlace: ['먼저 <b>거주하고 계신 지자체(시·군·구)</b>를 알려 주세요. 지역마다 수수료가 달라요. 지역을 고르면 <b>{x}</b> 수수료를 바로 안내해 드릴게요.',
      'First, please tell me <b>your city, county or district</b> — fees differ by area. I’ll answer <b>{x}</b> right after you choose.',
      '请先告诉我<b>您居住的市、郡或区</b>，各地区费用不同。选好地区后马上为您说明<b>{x}</b>。',
      'Trước tiên, hãy cho biết <b>thành phố/quận nơi bạn sống</b> — mỗi nơi phí khác nhau. Chọn xong tôi sẽ trả lời <b>{x}</b> ngay.',
      'กรุณาบอก<b>เมือง/เขตที่คุณอาศัยอยู่</b>ก่อน เพราะค่าธรรมเนียมต่างกันตามพื้นที่ เลือกแล้วจะแจ้ง <b>{x}</b> ทันที',
      'Сначала укажите <b>ваш город или район</b> — тарифы везде разные. Как выберете, сразу отвечу про <b>{x}</b>.'],
    retryItem: ['품목 이름을 다시 입력해 주세요.', 'Please enter the item name again.', '请重新输入物品名称。', 'Vui lòng nhập lại tên đồ vật.', 'กรุณาพิมพ์ชื่อสิ่งของอีกครั้ง', 'Введите название предмета ещё раз.'],
    tryLater: ['잠시 후 다시 시도해 주세요.', 'Please try again in a moment.', '请稍后再试。', 'Vui lòng thử lại sau.', 'กรุณาลองใหม่อีกครั้ง', 'Попробуйте ещё раз чуть позже.'],
    feeLead: ['문의하신 품목의 수수료입니다.', 'Here are the fees for your items.', '以下是您查询物品的处理费。', 'Đây là phí cho đồ vật bạn hỏi.', 'ค่าธรรมเนียมของสิ่งของที่คุณถาม', 'Стоимость вывоза для ваших предметов.'],
    colItem: ['품목', 'Item', '物品', 'Đồ vật', 'สิ่งของ', 'Предмет'],
    colSpec: ['규격', 'Size', '规格', 'Kích thước', 'ขนาด', 'Размер'],
    colFee: ['수수료', 'Fee', '费用', 'Phí', 'ค่าธรรมเนียม', 'Плата'],
    pickHint: ['규격이 여러 개인 품목은 해당하는 규격을 하나 골라 주세요.', 'For items with several sizes, tap the one that matches.', '有多个规格的物品，请选择对应的一项。', 'Đồ có nhiều kích thước, hãy chọn một mục phù hợp.', 'สิ่งของที่มีหลายขนาด กรุณาเลือกขนาดที่ตรง', 'Если размеров несколько, выберите подходящий.'],
    addCart: ['장바구니에 담기', 'Add to cart', '加入购物车', 'Thêm vào giỏ', 'ใส่ตะกร้า', 'В корзину'],
    pickFirst: ['규격을 골라 주세요: {x}', 'Please choose a size: {x}', '请选择规格：{x}', 'Vui lòng chọn kích thước: {x}', 'กรุณาเลือกขนาด: {x}', 'Выберите размер: {x}'],
    added: ['장바구니에 {n}개 담았습니다', 'Added {n} to the cart', '已加入购物车 {n} 件', 'Đã thêm {n} món vào giỏ', 'ใส่ตะกร้าแล้ว {n} รายการ', 'Добавлено в корзину: {n}'],
    cartEmpty: ['장바구니가 비어 있습니다.', 'Your cart is empty.', '购物车是空的。', 'Giỏ đang trống.', 'ตะกร้าว่าง', 'Корзина пуста.'],
    cartEmptySub: ['수수료 안내 아래 ‘장바구니에 담기’를 누르면 여기에 모입니다.', 'Tap “Add to cart” under a fee answer to collect items here.', '在费用说明下点击“加入购物车”即可收集到这里。', 'Bấm “Thêm vào giỏ” dưới phần phí để gom đồ vào đây.', 'กด “ใส่ตะกร้า” ใต้ค่าธรรมเนียมเพื่อรวมรายการไว้ที่นี่', 'Нажмите «В корзину» под ответом, чтобы собрать предметы здесь.'],
    cartTitle: ['장바구니', 'Cart', '购物车', 'Giỏ', 'ตะกร้า', 'Корзина'],
    total: ['합계', 'Total', '合计', 'Tổng', 'รวม', 'Итого'],
    noFee: ['무상수거 등 금액이 없는 품목 {n}개는 합계에서 빠졌습니다.', '{n} item(s) without a fee (e.g. free pickup) are not in the total.', '{n} 件无费用物品（如免费回收）未计入合计。', '{n} món không có phí (vd: thu gom miễn phí) không tính vào tổng.', 'ไม่รวม {n} รายการที่ไม่มีค่าธรรมเนียม (เช่น เก็บฟรี)', 'Не включено в итог: {n} (бесплатный вывоз и т. п.).'],
    unitWarn: ['면적·길이·무게 단위로 매기거나 추가 요금이 붙는 품목이 있어 실제 금액은 달라질 수 있습니다.', 'Some items are charged by area, length or weight, or have extra charges, so the actual amount may differ.', '部分物品按面积、长度、重量计费或有附加费，实际金额可能不同。', 'Một số món tính theo diện tích, chiều dài, cân nặng hoặc có phụ phí nên số tiền thực tế có thể khác.', 'บางรายการคิดตามพื้นที่ ความยาว น้ำหนัก หรือมีค่าเพิ่ม ยอดจริงอาจต่างไป', 'Часть предметов оплачивается по площади, длине или весу либо с доплатой — итог может отличаться.'],
    unitQty: ['수량에 단위 수를 넣어 주세요', 'Enter the number of units as quantity', '数量请填写单位数', 'Nhập số đơn vị vào số lượng', 'ใส่จำนวนหน่วยในช่องจำนวน', 'Укажите количество единиц'],
    copy: ['복사', 'Copy', '复制', 'Sao chép', 'คัดลอก', 'Копировать'],
    excel: ['엑셀 내려받기', 'Download Excel', '下载 Excel', 'Tải Excel', 'ดาวน์โหลด Excel', 'Скачать Excel'],
    clear: ['비우기', 'Clear', '清空', 'Xóa hết', 'ล้าง', 'Очистить'],
    copied: ['복사했습니다', 'Copied', '已复制', 'Đã sao chép', 'คัดลอกแล้ว', 'Скопировано'],
    cartCopied: ['장바구니를 복사했습니다', 'Cart copied', '已复制购物车', 'Đã sao chép giỏ', 'คัดลอกตะกร้าแล้ว', 'Корзина скопирована'],
    cartCleared: ['지역이 바뀌어 장바구니를 비웠습니다', 'Area changed, so the cart was cleared', '地区已更改，购物车已清空', 'Đã đổi khu vực nên giỏ đã được xóa', 'เปลี่ยนพื้นที่แล้ว จึงล้างตะกร้า', 'Район изменён — корзина очищена'],
    dlFail: ['내려받지 못했습니다', 'Download failed', '下载失败', 'Tải xuống thất bại', 'ดาวน์โหลดไม่สำเร็จ', 'Не удалось скачать'],
    pendLead: ['확인 후 안내드리겠습니다.', 'We’ll check and let you know.', '我们确认后通知您。', 'Chúng tôi sẽ kiểm tra rồi báo cho bạn.', 'จะตรวจสอบแล้วแจ้งให้ทราบ', 'Мы уточним и сообщим вам.'],
    pendSub: ['이름과 휴대폰 번호를 남겨 주시면 확인되는 대로 문자로 알려 드립니다.', 'Leave your name and mobile number and we’ll text you once it’s confirmed.', '留下姓名和手机号码，确认后会短信通知您。', 'Để lại tên và số điện thoại, chúng tôi sẽ nhắn tin khi có kết quả.', 'ฝากชื่อและเบอร์มือถือไว้ จะส่ง SMS แจ้งเมื่อยืนยันแล้ว', 'Оставьте имя и номер телефона — пришлём SMS, когда уточним.'],
    name: ['이름', 'Name', '姓名', 'Tên', 'ชื่อ', 'Имя'],
    phone: ['휴대폰 번호', 'Mobile number', '手机号码', 'Số điện thoại', 'เบอร์มือถือ', 'Номер телефона'],
    agree: ['[필수] 안내 문자 발송을 위해 이름·휴대폰 번호를 수집·이용하는 데 동의합니다. (보관 90일 후 파기)', '[Required] I agree that my name and mobile number are collected and used to send the reply text. (Deleted after 90 days)', '[必选] 同意为发送通知短信收集和使用姓名、手机号码。（保存90天后删除）', '[Bắt buộc] Tôi đồng ý cho thu thập, sử dụng tên và số điện thoại để gửi tin nhắn. (Xóa sau 90 ngày)', '[จำเป็น] ยินยอมให้เก็บและใช้ชื่อ เบอร์มือถือ เพื่อส่ง SMS แจ้ง (ลบหลัง 90 วัน)', '[Обязательно] Согласен на сбор и использование имени и номера для отправки SMS. (Удаляются через 90 дней)'],
    getSms: ['문자로 받기', 'Get a text', '短信接收', 'Nhận tin nhắn', 'รับทาง SMS', 'Получить SMS'],
    ticket: ['접수번호', 'Ticket no.', '受理编号', 'Mã tiếp nhận', 'หมายเลขรับเรื่อง', 'Номер заявки'],
    copyLink: ['확인 주소 복사', 'Copy check link', '复制查询链接', 'Sao chép link kiểm tra', 'คัดลอกลิงก์ตรวจสอบ', 'Скопировать ссылку'],
    linkCopied: ['확인 주소를 복사했습니다', 'Link copied', '已复制链接', 'Đã sao chép link', 'คัดลอกลิงก์แล้ว', 'Ссылка скопирована'],
    errName: ['이름을 입력해 주세요.', 'Please enter your name.', '请输入姓名。', 'Vui lòng nhập tên.', 'กรุณากรอกชื่อ', 'Введите имя.'],
    errPhone: ['휴대폰 번호를 확인해 주세요. (예: 010-1234-5678)', 'Please check the mobile number. (e.g. 010-1234-5678)', '请确认手机号码。（例：010-1234-5678）', 'Vui lòng kiểm tra số điện thoại. (vd: 010-1234-5678)', 'กรุณาตรวจสอบเบอร์มือถือ (เช่น 010-1234-5678)', 'Проверьте номер. (напр. 010-1234-5678)'],
    errAgree: ['개인정보 수집·이용에 동의해 주세요.', 'Please agree to the collection and use of your information.', '请同意收集和使用个人信息。', 'Vui lòng đồng ý thu thập, sử dụng thông tin cá nhân.', 'กรุณายินยอมการเก็บและใช้ข้อมูลส่วนบุคคล', 'Дайте согласие на обработку данных.'],
    step: ['질문 {a}/{b}', 'Question {a}/{b}', '问题 {a}/{b}', 'Câu hỏi {a}/{b}', 'คำถาม {a}/{b}', 'Вопрос {a}/{b}'],
    asItem: ['“{n}”은(는) <b>‘{l}’</b> 항목으로 내놓으시면 됩니다. 이대로 안내해 드릴까요?', '“{n}” goes out as <b>“{l}”</b>. Shall I show that fee?', '“{n}”请按<b>“{l}”</b>类别投放。按此说明吗？', '“{n}” được bỏ theo mục <b>“{l}”</b>. Hướng dẫn theo mục này nhé?', '“{n}” ทิ้งในหมวด <b>“{l}”</b> ให้แจ้งตามนี้ไหม?', '«{n}» выносится как <b>«{l}»</b>. Показать эту плату?'],
    isItem: ['“{n}” — 문의하신 품목이 <b>{l}</b> 맞으신가요?', '“{n}” — is your item a <b>{l}</b>?', '“{n}”—您询问的物品是<b>{l}</b>吗？', '“{n}” — đồ của bạn có phải là <b>{l}</b> không?', '“{n}” — สิ่งของของคุณคือ <b>{l}</b> ใช่ไหม?', '«{n}» — ваш предмет: <b>{l}</b>?'],
    chooseSize: ['크기를 골라 주세요', 'Choose the size', '请选择大小', 'Chọn kích thước', 'เลือกขนาด', 'Выберите размер'],
    yes: ['예', 'Yes', '是', 'Có', 'ใช่', 'Да'],
    no: ['아니요', 'No', '不是', 'Không', 'ไม่ใช่', 'Нет'],
    other: ['기타(직접 입력)', 'Other (type it)', '其他（直接输入）', 'Khác (tự nhập)', 'อื่น ๆ (พิมพ์เอง)', 'Другое (введите)'],
    ok: ['확인', 'OK', '确认', 'OK', 'ตกลง', 'OK'],
    photo: ['사진', 'Photo', '照片', 'Ảnh', 'รูปภาพ', 'Фото'],
    w: ['가로(cm)', 'Width (cm)', '宽(cm)', 'Rộng (cm)', 'กว้าง (ซม.)', 'Ширина (см)'],
    d: ['세로(cm)', 'Depth (cm)', '深(cm)', 'Sâu (cm)', 'ลึก (ซม.)', 'Глубина (см)'],
    h: ['높이(cm)', 'Height (cm)', '高(cm)', 'Cao (cm)', 'สูง (ซม.)', 'Высота (см)'],
    describe: ['어떤 물건인지 한두 마디(선택)', 'Describe it in a few words (optional)', '简单描述一下（可选）', 'Mô tả ngắn (không bắt buộc)', 'อธิบายสั้น ๆ (ไม่บังคับ)', 'Пара слов о предмете (необязательно)'],
    needPhoto: ['사진이나 크기 중 하나는 알려 주세요.', 'Please give a photo or the size.', '请提供照片或尺寸。', 'Vui lòng gửi ảnh hoặc kích thước.', 'กรุณาส่งรูปหรือขนาด', 'Пришлите фото или размеры.'],
    dunno: ['잘 모르겠어요', 'Not sure', '不太清楚', 'Không rõ', 'ไม่แน่ใจ', 'Не знаю'],
    photoOne: ['사진 1장', '1 photo', '1张照片', '1 ảnh', 'รูป 1 รูป', '1 фото'],
    ticketHead: ['접수번호 {t} · {m}', 'Ticket {t} · {m}', '受理编号 {t} · {m}', 'Mã {t} · {m}', 'หมายเลข {t} · {m}', 'Заявка {t} · {m}'],
    pendLater: ['{x} — 확인 후 안내드리겠습니다.', '{x} — we’ll check and let you know.', '{x} — 确认后通知您。', '{x} — sẽ kiểm tra rồi báo bạn.', '{x} — จะตรวจสอบแล้วแจ้ง', '{x} — уточним и сообщим.'],
    closed: ['{x} — 지자체 담당 부서로 문의해 주세요.', '{x} — please ask the local government office.', '{x} — 请咨询当地政府主管部门。', '{x} — vui lòng hỏi cơ quan địa phương.', '{x} — กรุณาสอบถามหน่วยงานท้องถิ่น', '{x} — обратитесь в местную администрацию.'],
    korean: ['한국어 이름', 'Korean name', '韩文名称', 'Tên tiếng Hàn', 'ชื่อภาษาเกาหลี', 'Название по-корейски'],
    cartTextHead: ['대형폐기물 수수료 장바구니 ({m})', 'Bulky waste fee cart ({m})', '大件垃圾处理费购物车（{m}）', 'Giỏ phí rác cồng kềnh ({m})', 'ตะกร้าค่าทิ้งขยะชิ้นใหญ่ ({m})', 'Корзина: вывоз крупных отходов ({m})'],
    minus: ['하나 빼기', 'one less', '减一个', 'bớt một', 'ลดหนึ่ง', 'на один меньше'],
    plus: ['하나 더하기', 'one more', '加一个', 'thêm một', 'เพิ่มหนึ่ง', 'на один больше'],
    remove: ['빼기', 'remove', '删除', 'xóa', 'ลบ', 'удалить'],
    etc: ['기타', 'Other', '其他', 'Khác', 'อื่น ๆ', 'Прочее'],
    otherRegion: ['지역을 바꾸기 전 답변이에요. 지금 지역에서 다시 물어봐 주세요.', 'This answer is for the previous area. Please ask again for the current area.', '这是更改地区之前的回答，请在当前地区重新询问。', 'Đây là câu trả lời cho khu vực trước. Vui lòng hỏi lại cho khu vực hiện tại.', 'คำตอบนี้เป็นของพื้นที่ก่อนหน้า กรุณาถามใหม่สำหรับพื้นที่ปัจจุบัน', 'Это ответ для прежнего района. Спросите снова для текущего района.'],
    home: ['처음으로', 'Home', '首页', 'Trang đầu', 'หน้าแรก', 'В начало'],
    chatLog: ['대화', 'Conversation', '对话', 'Hội thoại', 'บทสนทนา', 'Диалог'],
    suggest: ['추천', 'Suggestions', '推荐', 'Gợi ý', 'คำแนะนำ', 'Подсказки'],
    cartCount: ['장바구니 {n}개', 'Cart, {n} items', '购物车 {n} 件', 'Giỏ, {n} món', 'ตะกร้า {n} รายการ', 'Корзина, предметов: {n}'],
    regionChange: ['{m}, 지역 변경', '{m}, change area', '{m}，更改地区', '{m}, đổi khu vực', '{m}, เปลี่ยนพื้นที่', '{m}, изменить район'],
    offline: ['인터넷 연결을 확인한 뒤 다시 시도해 주세요.', 'Please check your internet connection and try again.', '请检查网络连接后重试。', 'Vui lòng kiểm tra kết nối mạng rồi thử lại.', 'กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่', 'Проверьте подключение к интернету и попробуйте снова.'],
    retry: ['다시 시도', 'Try again', '重试', 'Thử lại', 'ลองใหม่', 'Повторить'],
    tooMany: ['한 번에 30개까지 안내합니다. 나머지 {n}개는 입력창에 남겨 두었어요.', 'Up to 30 items at a time. The other {n} are left in the input box.', '一次最多30件，其余{n}件留在输入框中。', 'Mỗi lần tối đa 30 món. {n} món còn lại vẫn ở ô nhập.', 'ครั้งละไม่เกิน 30 รายการ อีก {n} รายการยังอยู่ในช่องพิมพ์', 'За раз — до 30 предметов. Остальные {n} оставлены в поле ввода.'],
    busy: ['답변을 준비하고 있어요. 잠시만 기다려 주세요.', 'Still preparing the answer — one moment.', '正在准备回答，请稍候。', 'Đang chuẩn bị câu trả lời, vui lòng chờ.', 'กำลังเตรียมคำตอบ กรุณารอสักครู่', 'Готовлю ответ, подождите.'],
    etcPay: ['기타 금액으로 결제:', 'Pay as “Other” amount:', '按“其他”金额支付：', 'Thanh toán mục “Khác”:', 'ชำระเป็นยอด “อื่น ๆ”:', 'Оплата как «Прочее»:']
  };
  var IDX = { ko: 0, en: 1, zh: 2, vi: 3, th: 4, ru: 5 };

  var cur = 'ko';
  try {
    cur = localStorage.getItem('bw.lang') || '';      // 언어는 이 기기에만 기억(지역은 기억하지 않음)
  } catch (e) { cur = ''; }
  if (!IDX.hasOwnProperty(cur)) {
    var nav = String((navigator.languages && navigator.languages[0]) || navigator.language || 'ko').slice(0, 2).toLowerCase();
    cur = IDX.hasOwnProperty(nav) ? nav : 'ko';
  }

  function t(key, vars) {
    var row = S[key];
    var s = row ? (row[IDX[cur]] || row[0]) : key;
    if (vars) Object.keys(vars).forEach(function (k) { s = s.split('{' + k + '}').join(vars[k]); });
    return s;
  }
  function set(code) {
    if (!IDX.hasOwnProperty(code)) return;
    cur = code;
    try { localStorage.setItem('bw.lang', code); } catch (e) { /* 무시 */ }
  }

  /* 답변 속 글 번역(한국어면 그대로). 같은 글은 한 번만 묻는다. */
  var memo = {}, tags = {};
  function addTags(tk) { if (tk) Object.keys(tk).forEach(function (k) { tags[k] = tk[k]; }); }
  function tr(texts, to) {
    var lang = to || cur;
    if (lang === 'ko' && !to) return Promise.resolve(texts.slice());
    var need = [];
    texts.forEach(function (x) { var k = lang + '|' + x; if (x && memo[k] === undefined && need.indexOf(x) < 0) need.push(x); });
    var done = function () { return texts.map(function (x) { var v = memo[lang + '|' + x]; return v === undefined ? x : v; }); };
    if (!need.length) return Promise.resolve(done());
    var parts = [];
    for (var i = 0; i < need.length; i += 60) parts.push(need.slice(i, i + 60));
    return Promise.all(parts.map(function (p) {
      var tk = {}; p.forEach(function (x) { if (tags[x]) tk[x] = tags[x]; });
      return fetch('/api/translate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lang: lang, texts: p, tk: tk }) })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {          // 실패(429 등)는 기억하지 않는다 → 다음에 다시 시도
          if (j && j.texts) j.texts.forEach(function (v, n) { if (v && v !== p[n]) memo[lang + '|' + p[n]] = v; });
        })
        .catch(function () { /* 다음에 다시 */ });
    })).then(done);
  }

  window.I18N = { LANGS: LANGS, flag: flag, t: t, set: set, tr: tr, addTags: addTags, lang: function () { return cur; } };
})();
