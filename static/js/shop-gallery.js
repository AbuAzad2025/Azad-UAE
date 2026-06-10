(function () {
  'use strict';
  var gallery = document.querySelector('.ps-product-gallery');
  if (!gallery) return;
  var mainImg = gallery.querySelector('.ps-gallery-main img');
  if (!mainImg) return;
  gallery.addEventListener('mousemove', function (e) {
    var rect = gallery.getBoundingClientRect();
    var x = ((e.clientX - rect.left) / rect.width) * 100;
    var y = ((e.clientY - rect.top) / rect.height) * 100;
    mainImg.style.transformOrigin = x + '% ' + y + '%';
    mainImg.style.transform = 'scale(2)';
  });
  gallery.addEventListener('mouseleave', function () {
    mainImg.style.transformOrigin = 'center center';
    mainImg.style.transform = 'scale(1)';
  });
  gallery.addEventListener('click', function () {
    var zoomed = mainImg.style.transform === 'scale(2)';
    mainImg.style.transform = zoomed ? 'scale(1)' : 'scale(2)';
    mainImg.style.transformOrigin = 'center center';
  });
})();
