# M14 – Global Search · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F12](../../features/F12-global-search.md)

## Chuẩn bị

- [ ] M12 xong: cụm có tóm tắt + `tom_tat_embedding`
- [ ] Cạnh chủ đề / đối tượng đủ cho `hoa_don_dien_tu` + `ho_kinh_doanh`
- [ ] Duyệt bổ sung trường `ContextItem.unit_ids`

## Triển khai

- [ ] M14-T1 Lọc đồ thị theo chủ đề + đối tượng, còn hiệu lực tại ngày, nhóm theo văn bản (F12 §6.1)
- [ ] M14-T1 Không có chủ đề / đối tượng → bỏ lọc đồ thị
- [ ] M14-T1 `GET /topics/{ma_chu_de}/documents?doi_tuong=&ngay=`
- [ ] M14-T2 Chọn cụm: vector `cum_embedding` top 5 ∪ cụm chứa Điều khớp; xếp theo số Điều khớp; ≤ 3; loại cụm tương đồng < 0.5 không chứa Điều khớp
- [ ] M14-T3 Map: tóm tắt + Điều còn hiệu lực tại ngày (≤ 2 500 token), `global_map` no-think, `MapOutput`
- [ ] M14-T3 Bỏ ý có `unit_ids` ngoài đầu vào; bỏ ý điểm < 30
- [ ] M14-T3 Ngày ≠ hôm nay → không đưa `tom_tat` vào prompt map
- [ ] M14-T4 Reduce: gộp, khử trùng theo `unit_ids`, top 15 → `ContextItem(tong_hop)` có `unit_ids`
- [ ] M14-T5 Hạn 20 s → `partial = true`; callback `on_progress`
- [ ] M14-T5 Notice văn bản cùng chủ đề hết hiệu lực trong 12 tháng
- [ ] M14-T5 Kết quả qua `EffectivityService.filter`
- [ ] M14-T5 `POST /search/global`
- [ ] M14-T6 Route `GLOBAL` trong pipeline dùng `GlobalSearcher`; không áp timeout 1.5 s

## Kiểm thử

- [ ] Mock LLM: ý `unit_id` lạ / điểm thấp bị bỏ
- [ ] Reduce khử trùng
- [ ] Mock LLM chậm → `partial = true` trong ≤ 20 s
- [ ] Ngày quá khứ không dùng `tom_tat`
- [ ] M14-T6 Golden Q3

## Tiêu chí chấp nhận (F12 §7)

- [ ] Q3: `structured_result` chứa NĐ 123 (đã sửa), NĐ 70/2025, TT 32/2025; không chứa TT 78/2021 (chỉ ở notice)
- [ ] Mọi `unit_ids` trong ngữ cảnh tổng hợp tồn tại và còn hiệu lực tại ngày áp dụng
- [ ] Global Search hoàn thành ≤ 20 s trên máy dev, hoặc trả `partial = true`

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Ghi thời gian map trung bình / cụm trên máy dev vào `docs/spikes/`
