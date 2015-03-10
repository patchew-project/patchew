% include('templates/header.tpl', title='Series', stylesheets=('thread.css',))

<ul class="nav nav-tabs">
    <li role="presentation" class="active"><a href="#">Thread</a></li>
    <li role="presentation"><a href="/testing/log/{{thread['message-id']}}">Testing</a></li>
</ul>
<br>

%def put_message(msg, lvl):
    <div class="panel panel-default message reply-lvl-{{min(lvl, 5)}}">
        <div class="panel-heading message-toggler">
            <h3 class="panel-title">
            {{msg['visible-subject']}}
            <span class="pull-right">
                <small>Posted by</small>
                <span class="message-author" title="{{msg['author-address']}}">{{msg['author']}}</span>
                <small>at</small>
                <span class="timestamp" title="{{msg['date']}}">{{msg['age']}}</span>
                <small>ago</small>
            </span>
            </h3>
        </div>
        <div class="panel-body">
            <span class="message-preview message-toggler message-toggle">{{msg['preview']}} ...</span>
            <pre class="body-full message-toggle">{{msg['body']}}</pre>
        </div>
    </div>
        %for m in msg['replies']:
            %put_message(m, lvl + 1)
        %end
%end

%put_message(thread, 0)

<script type="text/javascript">

function main() {
    $(".message-toggler").click(function () {
        $(this).parent().find(".message-toggle").toggle();
    });
    $(".timestamp").each(function (i, o) {
        $(o).attr("title", new Date(1000 * $(o).attr("title")));
    });
}

$(main);

</script>
% include('templates/footer.tpl')
