// Issues a POST for controls that change state, so those routes never have to
// accept GET. A GET-reachable delete or role change can be fired by anything that
// makes a browser fetch a URL - an <img> tag in a mail, a link scanner, a prefetch -
// without the user ever clicking. See issue #84.
//
// Usage: put the target URL in data-post on any clickable element.
//   <button type="button" class="dropdown-item" data-post="{{ url_for(...) }}">
//
// For a control that confirms first, skip data-post and call postTo() from the
// confirmation handler instead.

function postTo(url) {
    var form = document.createElement("form");
    form.method = "post";
    form.action = url;
    document.body.appendChild(form);
    form.submit();
}

document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-post]");
    if (!trigger) {
        return;
    }
    event.preventDefault();
    postTo(trigger.getAttribute("data-post"));
});
