package main

import ("net/http/httptest"; "testing")

func TestInjectedFailuresAreBounded(t *testing.T) {
	s := &service{failAfter: 2}
	for i := 0; i < 5; i++ { r := httptest.NewRequest("GET", "/work", nil); w := httptest.NewRecorder(); s.work(w, r); if i >= 2 && i < 5 && w.Code != 503 { t.Fatalf("request %d: got %d", i, w.Code) } }
}
